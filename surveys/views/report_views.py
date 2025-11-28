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
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.db.models import Count, Avg, Q, Min, Max
from django.db.models.functions import TruncDate
from django.core.cache import cache
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
        
        stats['satisfaction_avg'] = round(sat_avg['avg'] or 0, 1)
        
        cache.set(cache_key, stats, CACHE_TIMEOUT_STATS)
    
    return stats


def _get_trend_data_fast(survey_id, days=14):
    """
    Get daily response counts using efficient SQL.
    """
    cache_key = f"survey_trend_{survey_id}_{days}"
    trend = cache.get(cache_key)
    
    if trend is None:
        from django.utils import timezone
        from datetime import timedelta
        
        start_date = timezone.now() - timedelta(days=days)
        
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
            trend = {
                'labels': [item['dia'].strftime('%Y-%m-%d') for item in daily_counts],
                'data': [item['count'] for item in daily_counts]
            }
        else:
            trend = {'labels': [], 'data': []}
        
        cache.set(cache_key, trend, CACHE_TIMEOUT_STATS)
    
    return trend


# ============================================================
# EXPORTACIÓN CSV
# ============================================================

@login_required
@ratelimit(key='user', rate='10/h', method='GET', block=True)
def export_survey_csv_view(request, pk):
    """Exportar resultados de encuesta a CSV."""
    
    survey = get_object_or_404(Survey, pk=pk, author=request.user)
    
    # Obtener todas las respuestas con prefetch optimizado
    respuestas = SurveyResponse.objects.filter(survey=survey).prefetch_related(
        'question_responses__question',
        'question_responses__selected_option'
    ).order_by('created_at')
    
    if not respuestas.exists():
        messages.warning(request, "No hay respuestas para exportar en esta encuesta.")
        return redirect('surveys:resultados', pk=pk)
    
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
    
    # Log de exportación
    logger.info(
        f"Exportación CSV exitosa",
        user_id=request.user.id,
        survey_id=survey.id,
        total_respuestas=respuestas.count()
    )
    
    return response


# ============================================================
# DASHBOARD DE RESULTADOS - OPTIMIZADO
# ============================================================

@login_required
def survey_results_view(request, pk):
    """
    Vista INDIVIDUAL de resultados - OPTIMIZADA.
    Usa caché agresivo y carga diferida.
    """
    
    # 1. Cargar encuesta con optimizaciones (una sola query)
    survey = get_object_or_404(
        Survey.objects.select_related('author').prefetch_related('questions__options'),
        pk=pk
    )
    
    # 2. Verificar permisos
    PermissionHelper.verify_encuesta_access(survey, request.user)
    
    # 3. Obtener estadísticas rápidas (cacheadas)
    quick_stats = _get_survey_quick_stats(pk, request.user.id)
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
        cache_key = f"survey_results_{pk}_{start}_{end}_{segment_col}_{segment_val}_{segment_demo}"
        use_base_filter = False  # Use filtered IDs
    else:
        # Sin filtros: usar caché base
        respuestas_qs = SurveyResponse.objects.filter(survey=survey)
        cache_key = f"survey_results_base_{pk}"
        use_base_filter = True  # Use direct survey_id (fastest)
    
    # 6. Obtener análisis (con caché)
    analysis_result = SurveyAnalysisService.get_analysis_data(
        survey, 
        respuestas_qs, 
        include_charts=True,
        cache_key=cache_key,
        use_base_filter=use_base_filter
    )
    
    # 7. Obtener tendencia (cacheada)
    trend_data = _get_trend_data_fast(pk, days=14) if not has_filters else None
    
    # Si hay filtros, calcular tendencia específica
    if has_filters and total_respuestas > 0:
        daily_counts = respuestas_qs.annotate(
            dia=TruncDate('created_at')
        ).values('dia').annotate(
            count=Count('id')
        ).order_by('dia')
        
        trend_data = {
            'labels': [item['dia'].strftime('%Y-%m-%d') for item in daily_counts],
            'data': [item['count'] for item in daily_counts]
        } if daily_counts else None
    
    # 8. Preparar datos para JSON (completo para gráficas)
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
            'avg': item.get('avg'),
            'estadisticas': item.get('estadisticas'),
            'opciones': item.get('opciones', []),
            'top_options': item.get('top_options', [])
        }
        for item in analysis_result['analysis_data']
    ]
    
    # 9. Top insights (ya filtrados)
    top_insights = [item for item in analysis_result['analysis_data'] if item.get('insight')][:3]
    
    # 10. Preguntas para filtro (con información demográfica)
    preguntas_filtro = list(
        survey.questions.values('id', 'text', 'type', 'is_demographic', 'demographic_type')
        .order_by('order')
    )
    
    context = {
        'survey': survey,
        'total_respuestas': total_respuestas,
        'nps_score': analysis_result['nps_data'].get('score', 0),
        'nps_data': analysis_result['nps_data'],
        'metrics': {
            'promedio_satisfaccion': quick_stats.get('satisfaction_avg') if not has_filters 
                else analysis_result.get('kpi_prom_satisfaccion', 0)
        },
        'analysis_data': analysis_result['analysis_data'],
        'analysis_data_json': json.dumps(analysis_data_json),
        'trend_data': json.dumps(trend_data) if trend_data else None,
        'top_insights': top_insights,
        'heatmap_image': analysis_result.get('heatmap_image'),
        'preguntas_filtro': preguntas_filtro,
        'filter_start': start,
        'filter_end': end,
        'filter_col': segment_col,
        'filter_val': segment_val,
        'filter_demo': segment_demo,
        'has_filters': has_filters,
        'ignored_questions': analysis_result.get('ignored_questions', []),
    }
    
    return render(request, 'surveys/results.html', context)


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
def survey_analysis_ajax(request, pk):
    """
    API endpoint para cargar análisis bajo demanda.
    Útil para carga diferida de gráficos pesados.
    """
    survey = get_object_or_404(Survey.objects.prefetch_related('questions__options'), pk=pk)
    
    try:
        PermissionHelper.verify_encuesta_access(survey, request.user)
    except Exception:
        return JsonResponse({'error': 'Sin permisos'}, status=403)
    
    # Usar caché base
    cache_key = f"survey_results_base_{pk}"
    respuestas_qs = SurveyResponse.objects.filter(survey=survey)
    
    analysis = SurveyAnalysisService.get_analysis_data(
        survey, respuestas_qs, include_charts=True, cache_key=cache_key,
        use_base_filter=True
    )
    
    return JsonResponse({
        'success': True,
        'analysis_data': analysis['analysis_data'],
        'nps_data': analysis['nps_data'],
        'heatmap_image': analysis.get('heatmap_image'),
        'ignored_questions': analysis.get('ignored_questions', []),
    })


@login_required
def debug_analysis_view(request, pk):
    """DEBUG only: return lightweight analysis summary for a survey (JSON)."""
    
    survey = get_object_or_404(Survey.objects.prefetch_related('questions__options'), pk=pk)
    PermissionHelper.verify_encuesta_access(survey, request.user)

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
    })


# --- Vista de agradecimiento ---
def survey_thanks_view(request):
    return render(request, 'surveys/thanks.html')


# --- Cambiar estado de encuesta ---
@login_required
def cambiar_estado_encuesta(request, pk):
    """
    Cambiar el estado de una encuesta (draft, active, closed).
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    survey = get_object_or_404(Survey, pk=pk, author=request.user)
    
    try:
        data = json.loads(request.body)
        nuevo_estado = data.get('status', data.get('estado'))
        
        # Validar estado
        estados_validos = ['draft', 'active', 'closed']
        if nuevo_estado not in estados_validos:
            return JsonResponse({'error': 'Estado no válido'}, status=400)
        
        # Actualizar estado
        estado_anterior = survey.status
        survey.status = nuevo_estado
        survey.save(update_fields=['status'])
        
        # Invalidar caché de estadísticas
        cache.delete(f"survey_quick_stats_{pk}")
        
        # Log del cambio
        log_data_change(
            'UPDATE',
            'Encuesta',
            survey.id,
            request.user.id,
            changes={'estado': f'{estado_anterior} → {nuevo_estado}'}
        )
        
        return JsonResponse({
            'success': True,
            'nuevo_estado': nuevo_estado,
            'mensaje': f'Estado actualizado a {dict(Survey.STATUS_CHOICES).get(nuevo_estado, nuevo_estado)}'
        })
        
    except Exception as e:
        logger.exception(f"Error al cambiar estado de encuesta {pk}: {e}")
        return JsonResponse({'error': str(e)}, status=500)
