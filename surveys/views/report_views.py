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
from django.core.serializers.json import DjangoJSONEncoder # <--- IMPORTANTE
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
        # Single efficient query for all basic stats
        stats = SurveyResponse.objects.filter(
            survey_id=survey_id
        ).aggregate(
            total=Count('id'),
            first_response=Min('created_at'),
            last_response=Max('created_at'),
        )
        
        # Get satisfaction average in one query
        sat_avg = QuestionResponse.objects.filter(
            survey_response__survey_id=survey_id,
            question__type='scale',
            numeric_value__isnull=False
        ).aggregate(avg=Avg('numeric_value'))
        
        # Convert to float to avoid Decimal serialization issues
        avg_val = sat_avg['avg']
        stats['satisfaction_avg'] = round(float(avg_val), 1) if avg_val is not None else 0
        
        cache.set(cache_key, stats, CACHE_TIMEOUT_STATS)
    
    return stats


def _get_trend_data_fast(survey_id, days=14):
    """
    Obtiene conteo diario de respuestas y promedio diario de satisfacción (solo preguntas de tipo 'scale').
    """
    cache_key = f"survey_trend_{survey_id}_{days}"
    trend = cache.get(cache_key)
    
    if trend is None:
        from django.utils import timezone
        from datetime import timedelta
        
        start_date = timezone.now() - timedelta(days=days)
        
        # 1) Conteo de respuestas por día
        daily_counts = list(
            SurveyResponse.objects.filter(
                survey_id=survey_id,
                created_at__gte=start_date
            ).annotate(
                dia=TruncDate('created_at')
            ).values('dia').annotate(
                count=Count('id')
            ).order_by('dia')
        )
        
        if daily_counts:
            labels = [item['dia'].strftime('%Y-%m-%d') for item in daily_counts]
            
            # 2) Promedio de satisfacción por día (preguntas 'scale')
            daily_satisfaction = list(
                QuestionResponse.objects.filter(
                    survey_response__survey_id=survey_id,
                    survey_response__created_at__gte=start_date,
                    question__type='scale',
                    numeric_value__isnull=False
                ).annotate(
                    dia=TruncDate('survey_response__created_at')
                ).values('dia').annotate(
                    avg_satisfaction=Avg('numeric_value')
                ).order_by('dia')
            )
            
            # Map and convert Decimals to floats explicitly
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
    Returns True if there are questions that are NOT marked with skip_from_analysis 
    that contain date-related keywords. This indicates the CSV had a date column.
    """
    # Changed cache key to v2 to invalidate old cached values from previous logic
    cache_key = f"survey_has_date_fields_v2_{survey_id}"
    has_dates = cache.get(cache_key)
    
    if has_dates is None:
        from surveys.models import Survey
        import unicodedata
        import re
        
        survey = Survey.objects.get(id=survey_id)
        
        # Keywords that indicate a date column
        DATE_KEYWORDS = [
            'fecha', 'date', 'created', 'creado', 'timestamp', 'hora', 'time',
            'marca temporal', 'marca_temporal',  # Google Forms standard
            'fecharespuesta', 'fecha_respuesta', 'fecha respuesta',
            'fechacheckout', 'fecha_checkout', 'fecha checkout',
            'fechavisita', 'fecha_visita', 'fecha visita',
            'fechacompra', 'fecha_compra', 'fecha compra',
            'fechacreacion', 'fecha_creacion', 'fecha creacion',
            'periodo', 'period'
        ]
        
        def normalize_text(text):
            if not text:
                return ''
            normalized = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
            return normalized.lower()
        
        def contains_keyword(normalized_text, keyword):
            keyword = keyword.lower()
            if ' ' in keyword:
                return keyword in normalized_text
            return re.search(r'\b' + re.escape(keyword) + r'\b', normalized_text) is not None
        
        # Check if any question is a date field (not completely skipped)
        has_dates = False
        for question in survey.questions.all():
            normalized_text = normalize_text(question.text or '')
            
            # If this question matches date keywords, it's a date field
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
        logger.warning(f"Intento de exportar CSV de encuesta inexistente: ID {public_id} desde IP {request.META.get('REMOTE_ADDR')} por usuario {request.user.username}")
        messages.error(request, "La encuesta solicitada no existe o fue eliminada.")
        return redirect('dashboard')
    
    # Obtener todas las respuestas con prefetch optimizado
    respuestas = SurveyResponse.objects.filter(survey=survey).prefetch_related(
        'question_responses__question',
        'question_responses__selected_option'
    ).order_by('created_at')
    
    if not respuestas.exists():
        messages.warning(request, "No hay respuestas para exportar en esta encuesta.")
        return redirect('surveys:results', public_id=public_id)
    
    # Crear respuesta HTTP con CSV
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    filename = f"{survey.title.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # Agregar BOM para Excel en español
    response.write('\ufeff')
    
    writer = csv.writer(response)
    
    # Obtener todas las preguntas en orden
    preguntas = list(
        survey.questions.prefetch_related('options')
        .all()
        .order_by('order')
    )
    
    # Escribir encabezados
    headers = ['ID_Respuesta', 'Fecha', 'Usuario']
    headers.extend([p.text for p in preguntas])
    writer.writerow(headers)
    
    # Escribir datos
    for respuesta in respuestas:
        row = [
            respuesta.id,
            respuesta.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            respuesta.user.username if respuesta.user else 'Anónimo'
        ]
        
        # Crear mapa de respuestas por pregunta
        respuestas_map = {}
        for rp in respuesta.question_responses.all():
            pregunta_id = rp.question.id
            
            # Determinar el valor según el tipo
            if rp.numeric_value is not None:
                valor = str(rp.numeric_value)
            elif rp.selected_option:
                valor = rp.selected_option.text
            elif rp.text_value:
                valor = rp.text_value
            else:
                valor = ''
            
            # Si ya existe una respuesta para esta pregunta (multi), concatenar
            if pregunta_id in respuestas_map:
                respuestas_map[pregunta_id] += f", {valor}"
            else:
                respuestas_map[pregunta_id] = valor
        
        # Agregar respuestas en el orden de las preguntas
        for pregunta in preguntas:
            row.append(respuestas_map.get(pregunta.id, ''))
        
        writer.writerow(row)
    
    # Log de exportación (formato seguro para logging estándar)
    logger.info(
        f"Exportación CSV exitosa user_id={request.user.id} survey_id={survey.id} total_respuestas={respuestas.count()}"
    )
    
    return response


# ============================================================
# DASHBOARD DE RESULTADOS - OPTIMIZADO
# ============================================================

@login_required
def survey_results_view(request, public_id):
    """
    Vista INDIVIDUAL de resultados - OPTIMIZADA.
    Usa caché agresivo y carga diferida.
    """
    
    # 1. Cargar encuesta con optimizaciones (una sola query)
    try:
        survey = get_object_or_404(
            Survey.objects.select_related('author').prefetch_related('questions__options'),
            public_id=public_id
        )
    except Http404:
        logger.warning(f"Intento de acceso a resultados de encuesta inexistente: ID {public_id} desde IP {request.META.get('REMOTE_ADDR')} por usuario {request.user.username}")
        return render(request, 'surveys/crud/not_found.html', {
            'survey_id': public_id,
            'message': 'La encuesta cuyos resultados intentas ver no existe o ha sido eliminada.'
        }, status=404)
    
    # 2. Verificar permisos
    PermissionHelper.verify_survey_access(survey, request.user)
    survey_id = survey.pk
    
    # 3. Obtener estadísticas rápidas (cacheadas)
    quick_stats = _get_survey_quick_stats(survey_id, request.user.id)
    total_respuestas = quick_stats['total']
    
    # 4. Procesar filtros de fecha (solo si hay filtros)
    start = request.GET.get('start')
    end = request.GET.get('end')
    segment_col = request.GET.get('segment_col', '').strip()
    segment_val = request.GET.get('segment_val', '').strip()
    segment_demo = request.GET.get('segment_demo', '').strip()
    
    has_filters = start or end or segment_col or segment_val or segment_demo
    
    # 5. Si hay filtros, aplicarlos (sin caché, son específicos)
    if has_filters:
        respuestas_qs = SurveyResponse.objects.filter(survey=survey)
        
        if start or end:
            respuestas_qs, _ = DateFilterHelper.apply_filters(respuestas_qs, start, end)
        
        # Aplicar filtros de segmentación
        if segment_col:
            respuestas_qs = _apply_segment_filter(
                respuestas_qs, survey, segment_col, segment_val, segment_demo
            )
        
        total_respuestas = respuestas_qs.count()
        
        # Para filtros, usar análisis sin caché (datos específicos)
        # CACHE KEY UPDATE: v13 to ensure clean state
        cache_key = f"survey_results_v13_{survey_id}_{start}_{end}_{segment_col}_{segment_val}_{segment_demo}"
        use_base_filter = False  # Use filtered IDs
    else:
        # Sin filtros: usar caché base
        respuestas_qs = SurveyResponse.objects.filter(survey=survey)
        # CACHE KEY UPDATE: v13 to ensure clean state
        cache_key = f"survey_results_base_v13_{survey_id}"
        use_base_filter = True  # Use direct survey_id (fastest)
    
    # 6. Detectar modo oscuro desde el query param 'theme'
    theme = request.GET.get('theme', '')
    dark_mode = theme == 'dark'
    # 6. Obtener análisis (con caché)
    analysis_result = SurveyAnalysisService.get_analysis_data(
        survey, 
        respuestas_qs, 
        include_charts=True,
        cache_key=cache_key,
        use_base_filter=use_base_filter,
        dark_mode=dark_mode
    )
    
    # 7. Obtener tendencia (cacheada)
    trend_data = _get_trend_data_fast(survey_id, days=14) if not has_filters else None
    
    # Si hay filtros, calcular tendencia específica (respuestas + satisfacción)
    if has_filters and total_respuestas > 0:
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
    
    # Helper to convert Decimal to float for JSON
    def to_float(val):
        if val is None: return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return val

    # 8. Preparar datos para JSON (completo para gráficas)
    # Convertimos explícitamente a float para evitar TypeError de JSON
    analysis_data_json = [
        {
            'id': item.get('id'),
            'text': item.get('text'),
            'type': item.get('type'),
            'order': item.get('order'),
            'chart_labels': item.get('chart_labels', []),
            'chart_data': item.get('chart_data', []),
            'insight': item.get('insight', ''),
            'total_respuestas': item.get('total_respuestas', 0),
            'avg': to_float(item.get('avg')),
            'estadisticas': {k: to_float(v) for k, v in item.get('estadisticas').items()} if item.get('estadisticas') else None,
            'opciones': item.get('opciones', []),
            'top_options': item.get('top_options', [])
        }
        for item in analysis_result['analysis_data']
    ]
    
    # 9. Top insights (ordenados por criticidad/impacto)
    STATE_PRIORITY = {
        'CRITICO': 3,
        'REGULAR': 2,
        'BUENO': 1,
        'EXCELENTE': 0,
    }

    def _insight_score(item):
        state = (item.get('state') or '').upper()
        base = STATE_PRIORITY.get(state, 0)
        avg = item.get('avg')
        extra = 0
        # Dentro del mismo estado, valores promedio más bajos se consideran más críticos
        if isinstance(avg, (int, float)):
            extra = -avg
        return (base, extra)

    candidate_insights = [item for item in analysis_result['analysis_data'] if item.get('insight')]
    candidate_insights.sort(key=_insight_score, reverse=True)
    top_insights = candidate_insights[:3]
    
    # 10. Preguntas para filtro (con información demográfica)
    preguntas_filtro = list(
        survey.questions.values('id', 'text', 'type', 'is_demographic', 'demographic_type')
        .order_by('order')
    )
    
    # FIX: Acceso defensivo a nps_data
    nps_data = analysis_result.get('nps_data', {'score': 0})
    
    context = {
        'survey': survey,
        'total_respuestas': total_respuestas,
        'nps_score': nps_data.get('score', 0),
        'nps_data': nps_data,
        'metrics': {
            'promedio_satisfaccion': round(float(analysis_result.get('kpi_prom_satisfaccion', 0)), 1)
        },
        'analysis_data': analysis_result['analysis_data'],
        # Usamos DjangoJSONEncoder como respaldo para fechas y otros tipos
        'analysis_data_json': json.dumps(analysis_data_json, cls=DjangoJSONEncoder),
        'trend_data': json.dumps(trend_data, cls=DjangoJSONEncoder) if trend_data else None,
        'top_insights': top_insights,
        'heatmap_image': analysis_result.get('heatmap_image'),
        'heatmap_image_dark': analysis_result.get('heatmap_image_dark'),
        'preguntas_filtro': preguntas_filtro,
        'filter_start': start,
        'filter_end': end,
        'filter_col': segment_col,
        'filter_val': segment_val,
        'filter_demo': segment_demo,
        'has_filters': has_filters,
        'ignored_questions': analysis_result.get('ignored_questions', []),
        'has_date_fields': _has_date_fields(survey_id),
        'data_quality': analysis_result.get('data_quality'),
    }
    
    return render(request, 'surveys/responses/results.html', context)


def _apply_segment_filter(respuestas_qs, survey, segment_col, segment_val, segment_demo):
    """Apply segmentation filters efficiently."""

    pregunta_filtro = None

    try:
        pregunta_id = int(segment_col)
        pregunta_filtro = survey.questions.filter(id=pregunta_id).first()
    except (ValueError, TypeError):
        pregunta_filtro = survey.questions.filter(text__icontains=segment_col).first()
    
    if not pregunta_filtro:
        return respuestas_qs
    
    q_filter = Q()
    
    # Lógica de filtro demográfico
    if segment_demo and getattr(pregunta_filtro, 'is_demographic', False):
        demo_type = (getattr(pregunta_filtro, 'demographic_type', '') or '').lower()
        
        if demo_type == 'age':
            age_map = {
                'age_18_24': '18-24', 'age_25_34': '25-34',
                'age_35_44': '35-44', 'age_45_64': '45-64', 'age_65_plus': '65+'
            }
            lookup = age_map.get(segment_demo, segment_demo)
            q_filter = Q(selected_option__text__icontains=lookup) | Q(text_value__icontains=lookup)
        
        elif demo_type == 'gender':
            gender_map = {
                'gender_male': ['male', 'man', 'hombre'],
                'gender_female': ['female', 'woman', 'mujer'],
                'gender_other': ['other', 'otro']
            }
            candidates = gender_map.get(segment_demo, [segment_demo])
            for cand in candidates:
                q_filter |= Q(selected_option__text__icontains=cand) | Q(text_value__icontains=cand)
        else:
            q_filter = Q(selected_option__text__icontains=segment_demo) | Q(text_value__icontains=segment_demo)
    
    elif segment_val:
        if pregunta_filtro.type == 'text':
            q_filter = Q(text_value__icontains=segment_val)
        elif pregunta_filtro.type in ['single', 'multi']:
            q_filter = Q(selected_option__text__icontains=segment_val)
        elif pregunta_filtro.type == 'scale':
            try:
                valor_num = float(segment_val)
                q_filter = Q(numeric_value=valor_num)
            except ValueError:
                q_filter = Q(pk__isnull=True)
        else:
            q_filter = Q(text_value__icontains=segment_val) | Q(selected_option__text__icontains=segment_val)
    
    if q_filter:
        respuestas_ids = QuestionResponse.objects.filter(
            question=pregunta_filtro
        ).filter(q_filter).values_list('survey_response_id', flat=True)
        respuestas_qs = respuestas_qs.filter(id__in=respuestas_ids)
    
    return respuestas_qs


# ============================================================
# API ENDPOINT: Análisis bajo demanda (AJAX)
# ============================================================

@login_required
def survey_analysis_ajax(request, public_id):
    """
    API endpoint para cargar análisis bajo demanda.
    Útil para carga diferida de gráficos pesados.
    """
    try:
        survey = get_object_or_404(Survey.objects.prefetch_related('questions__options'), public_id=public_id)
    except Http404:
        logger.warning(f"Intento AJAX de acceso a análisis de encuesta inexistente: ID {public_id} desde IP {request.META.get('REMOTE_ADDR')} por usuario {request.user.username}")
        return JsonResponse({'error': 'Encuesta no encontrada'}, status=404)
    
    try:
        PermissionHelper.verify_survey_access(survey, request.user)
    except Exception:
        return JsonResponse({'error': 'Sin permisos'}, status=403)
    
    # Usar caché base (v12)
    cache_key = f"survey_results_base_v12_{survey.pk}"
    respuestas_qs = SurveyResponse.objects.filter(survey=survey)
    
    analysis = SurveyAnalysisService.get_analysis_data(
        survey, respuestas_qs, include_charts=True, cache_key=cache_key,
        use_base_filter=True
    )
    
    return JsonResponse({
        'success': True,
        'analysis_data': analysis['analysis_data'],
        'nps_data': analysis.get('nps_data', {'score': 0}),
        'heatmap_image': analysis.get('heatmap_image'),
        'heatmap_image_dark': analysis.get('heatmap_image_dark'),
        'ignored_questions': analysis.get('ignored_questions', []),
    }, encoder=DjangoJSONEncoder) # Encoder en JsonResponse también


@login_required
def debug_analysis_view(request, public_id):
    """DEBUG only: return lightweight analysis summary for a survey (JSON)."""
    
    try:
        survey = get_object_or_404(Survey.objects.prefetch_related('questions__options'), public_id=public_id)
    except Http404:
        logger.warning(f"Intento DEBUG de acceso a encuesta inexistente: ID {public_id} desde IP {request.META.get('REMOTE_ADDR')} por usuario {request.user.username}")
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


# --- Vista de agradecimiento ---
def survey_thanks_view(request):
    """Thank-you page that adapts content to survey status.

    Accepts optional query params:
    - public_id: survey identifier to link back if needed
    - status: one of draft|active|paused|closed
    - success: '1' when a response was recorded successfully
    """
    status = (request.GET.get('status') or '').lower()
    success = request.GET.get('success') == '1'
    public_id = request.GET.get('public_id')
    survey_title = None
    if public_id:
        try:
            s = Survey.objects.only('title').filter(public_id=public_id).first()
            if s:
                survey_title = s.title
        except Exception:
            survey_title = None

    # Default to active success if unspecified
    if not status and success:
        status = 'active'

    # Build UI hints
    messages_map = {
        'active_success': {
            'icon': 'check-circle-fill',
            'color': 'success',
            'title': '¡Gracias por tu respuesta!',
            'text': 'Tu opinión ha sido registrada con éxito y es muy valiosa para nosotros.'
        },
        'paused': {
            'icon': 'pause-circle-fill',
            'color': 'secondary',
            'title': 'Encuesta en pausa',
            'text': 'Este formulario no acepta respuestas por el momento. Intenta más tarde.'
        },
        'draft': {
            'icon': 'tools',
            'color': 'warning',
            'title': 'Encuesta en preparación',
            'text': 'El autor aún está configurando esta encuesta. Vuelve pronto.'
        },
        'closed': {
            'icon': 'lock-fill',
            'color': 'danger',
            'title': 'Encuesta finalizada',
            'text': 'Este formulario dejó de aceptar respuestas. ¡Gracias por tu interés!'
        }
    }

    key = 'active_success' if success and status == 'active' else status
    ui = messages_map.get(key) or messages_map['active_success']

    context = {
        'status': status or 'active',
        'success': success,
        'public_id': public_id,
        'ui': ui,
        'survey_title': survey_title,
    }
    return render(request, 'surveys/responses/thanks.html', context)


# --- Cambiar estado de encuesta ---
@login_required
def change_survey_status(request, public_id):
    """
    Change the status of a survey (draft, active, closed).
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    try:
        survey = get_object_or_404(Survey, public_id=public_id, author=request.user)
    except Http404:
        logger.warning(f"Intento de cambiar estado de encuesta inexistente: ID {public_id} desde IP {request.META.get('REMOTE_ADDR')} por usuario {request.user.username}")
        return JsonResponse({'error': 'Encuesta no encontrada'}, status=404)
    
    # Verificar si la encuesta es importada
    if survey.is_imported:
        logger.warning(f"Intento de cambiar estado de encuesta importada: ID {public_id} por usuario {request.user.username}")
        return JsonResponse({
            'error': 'Las encuestas importadas desde CSV no pueden cambiar de estado. Permanecen siempre activas.'
        }, status=403)
    
    try:
        data = json.loads(request.body)
        new_status = data.get('status', data.get('estado'))
        valid_statuses = {code for code, _ in Survey.STATUS_CHOICES}
        if new_status not in valid_statuses:
            return JsonResponse({'error': 'Estado no válido'}, status=400)

        previous_status = survey.status
        if new_status == previous_status:
            return JsonResponse({'success': True, 'new_status': new_status})

        try:
            survey.validate_status_transition(new_status)
        except ValidationError as exc:
            return JsonResponse({'error': str(exc)}, status=400)

        survey.status = new_status
        survey.save(update_fields=['status'])
        cache.delete(f"survey_quick_stats_{survey.pk}")
        log_data_change(
            'UPDATE',
            'Survey',
            survey.id,
            request.user.id,
            changes={'status': f'{previous_status} → {new_status}'}
        )
        return JsonResponse({
            'success': True,
            'new_status': new_status,
            'mensaje': f'Estado actualizado a {dict(Survey.STATUS_CHOICES).get(new_status, new_status)}'
        })
    except Exception as e:
        logger.exception(f"Error al cambiar estado de encuesta {public_id}: {e}")
        return JsonResponse({'error': str(e)}, status=500)