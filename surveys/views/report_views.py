import logging
import csv
import json
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.db.models import Count, Avg, Q
from django.db.models.functions import TruncDate
from django_ratelimit.decorators import ratelimit

from surveys.models import Survey, SurveyResponse, QuestionResponse
from core.utils.logging_utils import StructuredLogger, log_data_change
from core.utils.helpers import PermissionHelper, DateFilterHelper
from core.services.survey_analysis import SurveyAnalysisService

logger = StructuredLogger('surveys')

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
# DASHBOARD DE RESULTADOS
# ============================================================

@login_required
def survey_results_view(request, pk):
    """
    Vista INDIVIDUAL de resultados de una encuesta específica.
    Incluye gráficos, estadísticas, filtros por fecha y segmentación.
    """
    
    # Cargar encuesta con optimizaciones
    survey = get_object_or_404(
        Survey.objects.prefetch_related('questions__options'),
        pk=pk
    )
    
    # Verificar permisos (Helper importado correctamente arriba)
    PermissionHelper.verify_encuesta_access(survey, request.user)
    
    # Obtener respuestas base
    respuestas_qs = SurveyResponse.objects.filter(survey=survey).select_related('survey')
    
    # Procesar filtros de fecha
    start = request.GET.get('start')
    end = request.GET.get('end')
    
    if start or end:
        respuestas_qs, _ = DateFilterHelper.apply_filters(respuestas_qs, start, end)
    
    # Procesar filtro de segmentación
    segment_col = request.GET.get('segment_col', '').strip()
    segment_val = request.GET.get('segment_val', '').strip()
    segment_demo = request.GET.get('segment_demo', '').strip()

    if segment_col:
        pregunta_filtro = None
        try:
            pregunta_id = int(segment_col)
            pregunta_filtro = survey.questions.filter(id=pregunta_id).first()
        except (ValueError, TypeError):
            pregunta_filtro = survey.questions.filter(text__icontains=segment_col).first()
            
        if pregunta_filtro:
            q_filter = Q()

            # Lógica de filtro demográfico
            if segment_demo and getattr(pregunta_filtro, 'is_demographic', False):
                demo_type = (getattr(pregunta_filtro, 'demographic_type', '') or '').lower()

                if demo_type == 'age':
                    age_map = {
                        'age_18_24': '18-24',
                        'age_25_34': '25-34',
                        'age_35_44': '35-44',
                        'age_45_64': '45-64',
                        'age_65_plus': '65+'
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
                    q = Q()
                    for cand in candidates:
                        q |= Q(selected_option__text__icontains=cand) | Q(text_value__icontains=cand)
                    q_filter = q
                else:
                    lookup = segment_demo
                    q_filter = Q(selected_option__text__icontains=lookup) | Q(text_value__icontains=lookup)

            elif segment_val:
                # Comportamiento clásico
                if pregunta_filtro.type == 'text':
                    q_filter = Q(text_value__icontains=segment_val)
                elif pregunta_filtro.type == 'single' or pregunta_filtro.type == 'multi':
                    q_filter = Q(selected_option__text__icontains=segment_val)
                elif pregunta_filtro.type == 'scale':
                    try:
                        valor_num = float(segment_val)
                        q_filter = Q(numeric_value=valor_num)
                    except ValueError:
                        q_filter = Q(pk__isnull=True)
                else:
                    q_filter = Q(text_value__icontains=segment_val) | Q(selected_option__text__icontains=segment_val)

            # Aplicar filtro
            respuestas_ids = QuestionResponse.objects.filter(question=pregunta_filtro).filter(q_filter).values_list('survey_response_id', flat=True)
            respuestas_qs = respuestas_qs.filter(id__in=respuestas_ids)
    
    total_respuestas = respuestas_qs.count()
    
    # Generar datos de análisis usando el servicio
    cache_key = f"survey_results_{pk}_{start or 'all'}_{end or 'all'}_{segment_col}_{segment_val}"
    
    analysis_result = SurveyAnalysisService.get_analysis_data(
        survey, 
        respuestas_qs, 
        include_charts=True,
        cache_key=cache_key
    )
    
    # Calcular métricas adicionales
    promedio_satisfaccion = 0
    preguntas_escala = survey.questions.filter(type='scale')
    if preguntas_escala.exists():
        vals = QuestionResponse.objects.filter(
            question__in=preguntas_escala,
            survey_response__in=respuestas_qs,
            numeric_value__isnull=False
        ).aggregate(avg=Avg('numeric_value'))
        promedio_satisfaccion = vals['avg'] or 0
    
    # Top 3 insights
    top_insights = [item for item in analysis_result['analysis_data'] if item.get('insight')][:3]
    
    # Gráfico de tendencia histórica
    trend_data = None
    if total_respuestas > 0:
        daily_counts = respuestas_qs.annotate(
            dia=TruncDate('created_at')
        ).values('dia').annotate(
            count=Count('id')
        ).order_by('dia')
        
        if daily_counts:
            trend_data = {
                'labels': [item['dia'].strftime('%Y-%m-%d') for item in daily_counts],
                'data': [item['count'] for item in daily_counts]
            }
    
    # Serializar analysis_data para JavaScript
    analysis_data_json = []
    for item in analysis_result['analysis_data']:
        # 🛠️ CORRECCIÓN: Usar directamente las listas que ya preparó el servicio
        # El servicio devuelve items con claves 'chart_labels' y 'chart_data' planas.
        chart_labels = item.get('chart_labels', [])
        chart_data = item.get('chart_data', [])
        
        analysis_data_json.append({
            'id': item.get('id'),
            'text': item.get('text'),
            'type': item.get('type'),
            'order': item.get('order'),
            'chart_labels': chart_labels,
            'chart_data': chart_data,
            'insight': item.get('insight', '')
        })
    
    context = {
        'survey': survey,
        'total_respuestas': total_respuestas,
        'nps_score': analysis_result['nps_data'].get('score', 0),
        'nps_data': analysis_result['nps_data'],
        'metrics': {
            'promedio_satisfaccion': round(promedio_satisfaccion, 1) if promedio_satisfaccion else None
        },
        'analysis_data': analysis_result['analysis_data'],
        'analysis_data_json': json.dumps(analysis_data_json),
        'trend_data': json.dumps(trend_data) if trend_data else None,
        'top_insights': top_insights,
        'heatmap_image': analysis_result.get('heatmap_image'),
        'preguntas_filtro': survey.questions.all().order_by('order'),
        'filter_start': start,
        'filter_end': end,
        'filter_col': segment_col,
        'filter_val': segment_val,
    }
    
    return render(request, 'surveys/results.html', context)


@login_required
def debug_analysis_view(request, pk):
    """DEBUG only: return lightweight analysis summary for a survey (JSON)."""
    
    survey = get_object_or_404(Survey.objects.prefetch_related('questions__options'), pk=pk)
    PermissionHelper.verify_encuesta_access(survey, request.user)

    respuestas_qs = SurveyResponse.objects.filter(survey=survey)
    analysis = SurveyAnalysisService.get_analysis_data(survey, respuestas_qs, include_charts=True)

    summary = []
    for q in analysis.get('analysis_data', []):
        summary.append({
            'id': q.get('id'),
            'text': q.get('text'),
            'type': q.get('type'),
            'chart_data_len': len(q.get('chart_data', [])) if q.get('chart_data') else 0,
            'has_chart_image': bool(q.get('chart_image')),
        })

    return JsonResponse({'survey_id': survey.id, 'summary': summary})


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