# surveys/views/report_views.py
"""
Optimized report views for survey results.
Uses aggressive caching and efficient SQL queries.
"""
import logging
import csv
import json
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse, Http404
from django.contrib import messages
from django.db.models import Count, Avg, Q, Min, Max
from django.db.models.functions import TruncDate
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django_ratelimit.decorators import ratelimit

from surveys.models import Survey, SurveyResponse, QuestionResponse
from core.utils.logging_utils import StructuredLogger, log_data_change
from core.utils.helpers import PermissionHelper, DateFilterHelper
from core.services.survey_analysis import SurveyAnalysisService

logger = StructuredLogger('surveys')

# Cache timeout constants
CACHE_TIMEOUT_STATS = 300  # 5 minutes for basic stats
CACHE_TIMEOUT_ANALYSIS = 1800  # 30 minutes for full analysis


def _get_survey_quick_stats(survey_id, user_id):
    """
    Get quick statistics using efficient SQL aggregation.
    Cached for fast repeat access.
    """
    cache_key = f"survey_quick_stats_{survey_id}"
    stats = cache.get(cache_key)
    
    if stats is None:
        stats = SurveyResponse.objects.filter(
            survey_id=survey_id
        ).aggregate(
            total=Count('id'),
            first_response=Min('created_at'),
            last_response=Max('created_at'),
        )
        
        sat_avg = QuestionResponse.objects.filter(
            survey_response__survey_id=survey_id,
            question__type='scale',
            numeric_value__isnull=False
        ).aggregate(avg=Avg('numeric_value'))
        
        avg_val = sat_avg['avg']
        stats['satisfaction_avg'] = round(float(avg_val), 1) if avg_val is not None else 0
        
        cache.set(cache_key, stats, CACHE_TIMEOUT_STATS)
    
    return stats


def _get_trend_data_fast(survey_id, days=None):
    """
    Obtiene conteo diario de respuestas y promedio diario de satisfacción.
    """
    days_suffix = f"{days}" if days else "all_history"
    cache_key = f"survey_trend_{survey_id}_{days_suffix}"
    trend = cache.get(cache_key)
    
    if trend is None:
        from django.utils import timezone
        from datetime import timedelta
        
        base_qs = SurveyResponse.objects.filter(survey_id=survey_id)
        
        if days:
            start_date = timezone.now() - timedelta(days=days)
            base_qs = base_qs.filter(created_at__gte=start_date)
        
        daily_counts = list(
            base_qs.annotate(
                dia=TruncDate('created_at')
            ).values('dia').annotate(
                count=Count('id')
            ).order_by('dia')
        )
        
        if daily_counts:
            labels = [item['dia'].strftime('%Y-%m-%d') for item in daily_counts]
            
            sat_filter = Q(
                survey_response__survey_id=survey_id,
                question__type='scale',
                numeric_value__isnull=False
            )
            if days:
                sat_filter &= Q(survey_response__created_at__gte=start_date)

            daily_satisfaction = list(
                QuestionResponse.objects.filter(sat_filter).annotate(
                    dia=TruncDate('survey_response__created_at')
                ).values('dia').annotate(
                    avg_satisfaction=Avg('numeric_value')
                ).order_by('dia')
            )
            
            sat_map = {}
            for item in daily_satisfaction:
                val = item['avg_satisfaction']
                sat_map[item['dia']] = round(float(val), 1) if val is not None else 0
            
            trend = {
                'labels': labels,
                'data': [item['count'] for item in daily_counts],
                'satisfaction': [sat_map.get(item['dia']) for item in daily_counts],
            }
        else:
            trend = {'labels': [], 'data': [], 'satisfaction': []}
        
        cache.set(cache_key, trend, CACHE_TIMEOUT_STATS)
    
    return trend


def _has_date_fields(survey_id):
    """
    Check if survey has date fields from the CSV import.
    """
    cache_key = f"survey_has_date_fields_v2_{survey_id}"
    has_dates = cache.get(cache_key)
    
    if has_dates is None:
        from surveys.models import Survey
        import unicodedata
        import re
        
        survey = Survey.objects.get(id=survey_id)
        
        DATE_KEYWORDS = [
            'fecha', 'date', 'created', 'creado', 'timestamp', 'hora', 'time',
            'marca temporal', 'marca_temporal',
            'fecharespuesta', 'fecha_respuesta', 'fecha respuesta',
            'fechacheckout', 'fecha_checkout', 'fecha checkout',
            'fechavisita', 'fecha_visita', 'fecha visita',
            'fechacompra', 'fecha_compra', 'fecha compra',
            'fechacreacion', 'fecha_creacion', 'fecha creacion',
            'periodo', 'period'
        ]
        
        def normalize_text(text):
            if not text: return ''
            normalized = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
            return normalized.lower()
        
        def contains_keyword(normalized_text, keyword):
            keyword = keyword.lower()
            if ' ' in keyword:
                return keyword in normalized_text
            return re.search(r'\b' + re.escape(keyword) + r'\b', normalized_text) is not None
        
        has_dates = False
        for question in survey.questions.all():
            normalized_text = normalize_text(question.text or '')
            if any(contains_keyword(normalized_text, kw) for kw in DATE_KEYWORDS):
                has_dates = True
                break
        
        cache.set(cache_key, has_dates, CACHE_TIMEOUT_STATS)
    
    return has_dates


# ============================================================
# EXPORTACIÓN CSV
# ============================================================

@login_required
@ratelimit(key='user', rate='10/h', method='GET', block=True)
def export_survey_csv_view(request, public_id):
    """Exportar resultados de encuesta a CSV."""
    try:
        survey = get_object_or_404(Survey, public_id=public_id, author=request.user)
    except Http404:
        logger.warning(f"Intento de exportar CSV inexistente: {public_id} - {request.user.username}")
        messages.error(request, "La encuesta solicitada no existe o fue eliminada.")
        return redirect('dashboard')
    
    respuestas = SurveyResponse.objects.filter(survey=survey).prefetch_related(
        'question_responses__question',
        'question_responses__selected_option'
    ).order_by('created_at')
    
    if not respuestas.exists():
        messages.warning(request, "No hay respuestas para exportar en esta encuesta.")
        return redirect('surveys:results', public_id=public_id)
    
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    filename = f"{survey.title.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')
    
    writer = csv.writer(response)
    preguntas = list(survey.questions.prefetch_related('options').all().order_by('order'))
    
    headers = ['ID_Respuesta', 'Fecha', 'Usuario']
    headers.extend([p.text for p in preguntas])
    writer.writerow(headers)
    
    for respuesta in respuestas:
        row = [
            respuesta.id,
            respuesta.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            respuesta.user.username if respuesta.user else 'Anónimo'
        ]
        
        respuestas_map = {}
        for rp in respuesta.question_responses.all():
            pregunta_id = rp.question.id
            if rp.numeric_value is not None:
                valor = str(rp.numeric_value)
            elif rp.selected_option:
                valor = rp.selected_option.text
            elif rp.text_value:
                valor = rp.text_value
            else:
                valor = ''
            
            if pregunta_id in respuestas_map:
                respuestas_map[pregunta_id] += f", {valor}"
            else:
                respuestas_map[pregunta_id] = valor
        
        for pregunta in preguntas:
            row.append(respuestas_map.get(pregunta.id, ''))
        
        writer.writerow(row)
    
    return response


# ============================================================
# DASHBOARD DE RESULTADOS - OPTIMIZADO
# ============================================================

@login_required
def survey_results_view(request, public_id):
    """
    Vista INDIVIDUAL de resultados - OPTIMIZADA CON SOPORTE DARK MODE.
    """
    try:
        survey = get_object_or_404(
            Survey.objects.select_related('author').prefetch_related('questions__options'),
            public_id=public_id
        )
    except Http404:
        return render(request, 'surveys/crud/not_found.html', {
            'survey_id': public_id,
            'message': 'La encuesta no existe o ha sido eliminada.'
        }, status=404)
    
    PermissionHelper.verify_survey_access(survey, request.user)
    survey_id = survey.pk
    
    # --- DETECCIÓN DE TEMA (COOKIE + GET) ---
    # Esto es vital para que ChartGenerator sepa qué colores usar
    theme = request.GET.get('theme') or request.COOKIES.get('theme', 'light')
    dark_mode = theme == 'dark'
    
    quick_stats = _get_survey_quick_stats(survey_id, request.user.id)
    total_respuestas = quick_stats['total']
    
    start = request.GET.get('start')
    end = request.GET.get('end')
    segment_col = request.GET.get('segment_col', '').strip()
    segment_val = request.GET.get('segment_val', '').strip()
    segment_demo = request.GET.get('segment_demo', '').strip()
    
    has_filters = start or end or segment_col or segment_val or segment_demo
    
    # Construcción de la key de caché incluyendo el TEMA
    # Si no incluimos 'dark_mode' en la key, Django servirá gráficos generados en modo light (texto negro)
    # a usuarios en modo dark (fondo negro), haciéndolos invisibles.
    base_cache_suffix = f"{survey_id}_{theme}" 
    
    if has_filters:
        respuestas_qs = SurveyResponse.objects.filter(survey=survey)
        if start or end:
            respuestas_qs, _ = DateFilterHelper.apply_filters(respuestas_qs, start, end)
        if segment_col:
            respuestas_qs = _apply_segment_filter(
                respuestas_qs, survey, segment_col, segment_val, segment_demo
            )
        total_respuestas = respuestas_qs.count()
        cache_key = f"survey_results_v15_{base_cache_suffix}_{start}_{end}_{segment_col}_{segment_val}_{segment_demo}"
        use_base_filter = False
    else:
        respuestas_qs = SurveyResponse.objects.filter(survey=survey)
        cache_key = f"survey_results_base_v15_{base_cache_suffix}"
        use_base_filter = True
    
    analysis_result = SurveyAnalysisService.get_analysis_data(
        survey, 
        respuestas_qs, 
        include_charts=True,
        cache_key=cache_key,
        use_base_filter=use_base_filter,
        dark_mode=dark_mode
    )
    
    trend_data = _get_trend_data_fast(survey_id, days=None) if not has_filters else None
    
    if has_filters and total_respuestas > 0:
        # Recálculo de tendencia si hay filtros (no cacheado globalmente)
        daily_counts_qs = respuestas_qs.annotate(
            dia=TruncDate('created_at')
        ).values('dia').annotate(
            count=Count('id')
        ).order_by('dia')
        
        daily_counts = list(daily_counts_qs)
        if daily_counts:
            labels = [item['dia'].strftime('%Y-%m-%d') for item in daily_counts]
            daily_satisfaction = list(
                QuestionResponse.objects.filter(
                    survey_response__in=respuestas_qs,
                    question__type='scale',
                    numeric_value__isnull=False
                ).annotate(
                    dia=TruncDate('survey_response__created_at')
                ).values('dia').annotate(
                    avg_satisfaction=Avg('numeric_value')
                ).order_by('dia')
            )
            sat_map = {}
            for item in daily_satisfaction:
                val = item['avg_satisfaction']
                sat_map[item['dia']] = round(float(val), 1) if val is not None else 0
            
            trend_data = {
                'labels': labels,
                'data': [item['count'] for item in daily_counts],
                'satisfaction': [sat_map.get(item['dia']) for item in daily_counts],
            }
        else:
            trend_data = None
    
    def to_float(val):
        if val is None: return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return val

    analysis_data_json = [
        {
            'id': item.get('id'),
            'text': item.get('text'),
            'type': item.get('type'),
            'chart_labels': item.get('chart_labels', []),
            'chart_data': item.get('chart_data', []),
            'total_respuestas': item.get('total_respuestas', 0),
        }
        for item in analysis_result['analysis_data']
    ]
    
    candidate_insights = [item for item in analysis_result['analysis_data'] if item.get('insight')]
    # Simple sort for insights priority
    candidate_insights.sort(key=lambda x: -1 if x.get('state') == 'CRITICO' else 0)
    top_insights = candidate_insights[:3]
    
    preguntas_filtro = list(
        survey.questions.values('id', 'text', 'type', 'is_demographic', 'demographic_type')
        .order_by('order')
    )
    
    context = {
        'survey': survey,
        'total_respuestas': total_respuestas,
        'nps_score': analysis_result.get('nps_data', {}).get('score', 0),
        'metrics': {
            'promedio_satisfaccion': round(float(analysis_result.get('kpi_prom_satisfaccion', 0)), 1)
        },
        'analysis_data': analysis_result['analysis_data'],
        'analysis_data_json': json.dumps(analysis_data_json, cls=DjangoJSONEncoder),
        'trend_data': json.dumps(trend_data, cls=DjangoJSONEncoder) if trend_data else None,
        'top_insights': top_insights,
        'heatmap_image': analysis_result.get('heatmap_image'), # Ya viene generado con el color correcto según dark_mode
        'preguntas_filtro': preguntas_filtro,
        'filter_start': start,
        'filter_end': end,
        'filter_col': segment_col,
        'filter_val': segment_val,
        'filter_demo': segment_demo,
        'has_filters': has_filters,
        'has_date_fields': _has_date_fields(survey_id),
        'data_quality': analysis_result.get('data_quality'),
           'meta': analysis_result.get('meta'),
           'evolution_chart': analysis_result.get('evolution_chart'),
           'ignored_questions': analysis_result.get('ignored_questions', []),
    }
    
    return render(request, 'surveys/responses/results.html', context)


def _apply_segment_filter(respuestas_qs, survey, segment_col, segment_val, segment_demo):
    """Apply segmentation filters efficiently."""
    try:
        pregunta_id = int(segment_col)
        pregunta_filtro = survey.questions.filter(id=pregunta_id).first()
    except (ValueError, TypeError):
        return respuestas_qs
    
    if not pregunta_filtro:
        return respuestas_qs
    
    q_filter = Q()
    if segment_demo:
        # Lógica simplificada de filtro demográfico
        q_filter = Q(selected_option__text__icontains=segment_demo) | Q(text_value__icontains=segment_demo)
    elif segment_val:
        if pregunta_filtro.type == 'scale':
            try:
                q_filter = Q(numeric_value=float(segment_val))
            except ValueError:
                pass
        else:
            q_filter = Q(text_value__icontains=segment_val) | Q(selected_option__text__icontains=segment_val)
    
    if q_filter:
        respuestas_ids = QuestionResponse.objects.filter(question=pregunta_filtro).filter(q_filter).values_list('survey_response_id', flat=True)
        respuestas_qs = respuestas_qs.filter(id__in=respuestas_ids)
    
    return respuestas_qs


@login_required
def survey_analysis_ajax(request, public_id):
    # AJAX también debe respetar el tema para regenerar gráficos si se solicita
    try:
        survey = get_object_or_404(Survey, public_id=public_id)
        PermissionHelper.verify_survey_access(survey, request.user)
        
        theme = request.GET.get('theme') or request.COOKIES.get('theme', 'light')
        dark_mode = theme == 'dark'
        
        cache_key = f"survey_results_base_v15_{survey.pk}_{theme}"
        respuestas_qs = SurveyResponse.objects.filter(survey=survey)
        
        analysis = SurveyAnalysisService.get_analysis_data(
            survey, respuestas_qs, include_charts=True, cache_key=cache_key,
            use_base_filter=True, dark_mode=dark_mode
        )
        
        return JsonResponse({
            'success': True,
            'analysis_data': analysis['analysis_data'],
            'heatmap_image': analysis.get('heatmap_image')
        }, encoder=DjangoJSONEncoder)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# ... Resto de vistas (debug_analysis_view, survey_thanks_view, etc) ...
# Asegúrate de mantener change_survey_status y otras funciones auxiliares tal como estaban en tu archivo original.

@login_required
def debug_analysis_view(request, public_id):
    try:
        survey = get_object_or_404(Survey.objects.prefetch_related('questions__options'), public_id=public_id)
    except Http404:
        return JsonResponse({'error': 'Encuesta no encontrada'}, status=404)
    
    PermissionHelper.verify_survey_access(survey, request.user)
    respuestas_qs = SurveyResponse.objects.filter(survey=survey)
    analysis = SurveyAnalysisService.get_analysis_data(survey, respuestas_qs, include_charts=True, use_base_filter=True)

    summary = []
    for q in analysis.get('analysis_data', []):
        summary.append({
            'id': q.get('id'),
            'text': q.get('text'),
            'type': q.get('type'),
            'chart_data_len': len(q.get('chart_data', [])) if q.get('chart_data') else 0,
            'has_chart_image': bool(q.get('chart_image')),
        })

    return JsonResponse({
        'survey_id': survey.id,
        'summary': summary,
        'ignored_questions': analysis.get('ignored_questions', [])
    }, encoder=DjangoJSONEncoder)


def survey_thanks_view(request):
    status = (request.GET.get('status') or '').lower()
    success = request.GET.get('success') == '1'
    public_id = request.GET.get('public_id')
    survey_title = None
    if public_id:
        try:
            s = Survey.objects.only('title').filter(public_id=public_id).first()
            if s: survey_title = s.title
        except Exception: survey_title = None

    if not status and success: status = 'active'

    messages_map = {
        'active_success': {'icon': 'check-circle-fill', 'color': 'success', 'title': '¡Gracias por tu respuesta!', 'text': 'Tu opinión ha sido registrada con éxito.'},
        'paused': {'icon': 'pause-circle-fill', 'color': 'secondary', 'title': 'Encuesta en pausa', 'text': 'Este formulario no acepta respuestas por el momento.'},
        'draft': {'icon': 'tools', 'color': 'warning', 'title': 'Encuesta en preparación', 'text': 'El autor aún está configurando esta encuesta.'},
        'closed': {'icon': 'lock-fill', 'color': 'danger', 'title': 'Encuesta finalizada', 'text': 'Este formulario dejó de aceptar respuestas.'}
    }

    key = 'active_success' if success and status == 'active' else status
    ui = messages_map.get(key) or messages_map['active_success']

    return render(request, 'surveys/responses/thanks.html', {
        'status': status or 'active', 'success': success, 'public_id': public_id, 'ui': ui, 'survey_title': survey_title
    })


@login_required
def change_survey_status(request, public_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    try:
        survey = get_object_or_404(Survey, public_id=public_id, author=request.user)
    except Http404:
        return JsonResponse({'error': 'Encuesta no encontrada'}, status=404)
    
    if survey.is_imported:
        return JsonResponse({'error': 'Las encuestas importadas no pueden cambiar de estado.'}, status=403)
    
    try:
        data = json.loads(request.body)
        new_status = data.get('status', data.get('estado'))
        if new_status not in dict(Survey.STATUS_CHOICES):
            return JsonResponse({'error': 'Estado no válido'}, status=400)

        if new_status == survey.status:
            return JsonResponse({'success': True, 'new_status': new_status})

        survey.validate_status_transition(new_status)
        previous_status = survey.status
        survey.status = new_status
        survey.save(update_fields=['status'])
        cache.delete(f"survey_quick_stats_{survey.pk}")
        
        log_data_change('UPDATE', 'Survey', survey.id, request.user.id, changes={'status': f'{previous_status} → {new_status}'})
        
        return JsonResponse({
            'success': True, 
            'new_status': new_status, 
            'mensaje': f'Estado actualizado a {dict(Survey.STATUS_CHOICES).get(new_status, new_status)}'
        })
    except Exception as e:
        logger.exception(f"Error al cambiar estado {public_id}: {e}")
        return JsonResponse({'error': str(e)}, status=500)