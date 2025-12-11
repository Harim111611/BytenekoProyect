"""
surveys/views/report_views.py
Optimized report views for survey results.
"""
import logging
import csv
import json
import os
import mimetypes
from datetime import datetime
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse, Http404
from django.contrib import messages
from django.template.loader import render_to_string
from django.db.models import Q, Count, Avg, Min, Max
from django.db.models.functions import TruncDate
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django_ratelimit.decorators import ratelimit

from surveys.models import Survey, SurveyResponse, QuestionResponse, ImportJob
from core.utils.logging_utils import StructuredLogger, log_data_change
from core.utils.helpers import PermissionHelper, DateFilterHelper
from core.services.survey_analysis import SurveyAnalysisService

logger = StructuredLogger('surveys')

# Cache timeout constants
CACHE_TIMEOUT_STATS = 300
CACHE_TIMEOUT_ANALYSIS = 1800

def _has_date_fields(survey_id):
    """Check if survey has date fields from the CSV import."""
    cache_key = f"survey_has_date_fields_v2_{survey_id}"
    has_dates = cache.get(cache_key)
    
    if has_dates is None:
        import unicodedata
        import re
        
        try:
            survey = Survey.objects.get(id=survey_id)
        except Survey.DoesNotExist:
            return False
        
        DATE_KEYWORDS = [
            'fecha', 'date', 'created', 'creado', 'timestamp', 'hora', 'time',
            'marca temporal', 'marca_temporal',
            'fecharespuesta', 'fecha_respuesta',
            'periodo', 'period'
        ]
        
        def normalize_text(text):
            if not text: return ''
            normalized = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode('ascii')
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

# ============================================================
# VISTAS PRINCIPALES
# ============================================================

@login_required
def survey_results_view(request, public_id):
    """
    Vista principal del Dashboard de Resultados.
    Orquesta los datos del Service y los pasa al Template.
    """
    try:
        survey = get_object_or_404(
            Survey.objects.select_related('author').prefetch_related('questions__options'),
            public_id=public_id
        )
    except Http404:
        return render(request, 'surveys/crud/not_found.html', {'survey_id': public_id}, status=404)
    
    PermissionHelper.verify_survey_access(survey, request.user)
    
    # --- 1. Filtros ---
    start = request.GET.get('start')
    end = request.GET.get('end')
    segment_col = request.GET.get('segment_col', '').strip()
    segment_val = request.GET.get('segment_val', '').strip()
    segment_demo = request.GET.get('segment_demo', '').strip()
    
    has_filters = bool(start or end or segment_col)
    
    respuestas_qs = SurveyResponse.objects.filter(survey=survey)
    
    if start or end:
        respuestas_qs, _ = DateFilterHelper.apply_filters(respuestas_qs, start, end)
        
    if segment_col:
        respuestas_qs = _apply_segment_filter(
            respuestas_qs, survey, segment_col, segment_val, segment_demo
        )

    # --- 2. Obtener Análisis del Servicio ---
    # Usamos cache key basada en filtros para evitar recálculos
    cache_key = f"analysis_view_v16_{survey.id}_{start}_{end}_{segment_col}_{segment_val}"
    
    analysis_result = SurveyAnalysisService.get_analysis_data(
        survey, 
        respuestas_qs, 
        include_charts=True,
        cache_key=cache_key
    )
    
    # --- 3. Preparar Contexto ---
    kpi_score = analysis_result.get('kpi_score', 0)
    evolution = analysis_result.get('evolution', {})
    
    # Identificar top insights
    insights_list = analysis_result.get('analysis_data', [])
    top_insights = [
        item for item in insights_list 
        if item.get('insight_data', {}).get('mood') in ['CRITICO', 'EXCELENTE']
    ][:3]

    # Preguntas disponibles para el filtro de segmentación
    preguntas_filtro = list(
        survey.questions.values('id', 'text', 'type', 'is_demographic')
        .order_by('order')
    )

    context = {
        'survey': survey,
        'total_respuestas': respuestas_qs.count(),
        'analysis_data': insights_list,
        'evolution_chart': json.dumps(evolution, cls=DjangoJSONEncoder),
        'kpi_score': round(float(kpi_score), 1),
        'has_filters': has_filters,
        'filter_start': start,
        'filter_end': end,
        'filter_col': segment_col,
        'filter_val': segment_val,
        'filter_demo': segment_demo,
        'preguntas_filtro': preguntas_filtro,
        'has_date_fields': _has_date_fields(survey.id),
        'top_insights': top_insights,
        'ignored_questions': analysis_result.get('ignored_questions', [])
    }
    
    return render(request, 'surveys/responses/results.html', context)


@login_required
def report_preview(request, public_id):
    """
    Vista AJAX para generar la previsualización en el Generador de Reportes.
    """
    try:
        survey = get_object_or_404(Survey, public_id=public_id)
        PermissionHelper.verify_survey_access(survey, request.user)
        
        # Filtros básicos de fecha si vienen en la petición
        start = request.POST.get('start_date') or request.GET.get('start_date')
        end = request.POST.get('end_date') or request.GET.get('end_date')
        window = request.POST.get('window_days') or request.GET.get('window_days')
        
        respuestas_qs = SurveyResponse.objects.filter(survey=survey)
        
        # Lógica simple de ventana si no hay fechas exactas
        if not start and window and window.isdigit():
            from django.utils import timezone
            from datetime import timedelta
            start_dt = timezone.now() - timedelta(days=int(window))
            respuestas_qs = respuestas_qs.filter(created_at__gte=start_dt)
        elif start or end:
            respuestas_qs, _ = DateFilterHelper.apply_filters(respuestas_qs, start, end)
        
        analysis = SurveyAnalysisService.get_analysis_data(
            survey, respuestas_qs, include_charts=True
        )
        
        html = render_to_string('core/reports/_report_preview_content.html', {
            'survey': survey,
            'analysis': analysis,
            'kpi_score': analysis.get('kpi_score', 0),
            'generated_at': datetime.now()
        }, request=request)
        
        return JsonResponse({'success': True, 'html': html})
        
    except Exception as e:
        logger.exception(f"Error generando preview reporte: {e}")
        return JsonResponse({'error': str(e)}, status=500)


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

    # Caso 1: Encuesta importada (Servir archivo original si existe)
    if getattr(survey, 'is_imported', False):
        import_job = (
            ImportJob.objects
            .filter(survey=survey, status="completed")
            .order_by('-created_at')
            .first()
        )

        if import_job and import_job.csv_file and os.path.exists(import_job.csv_file):
            import_path = import_job.csv_file
            original_filename = import_job.original_filename or os.path.basename(import_path)

            with open(import_path, 'rb') as f:
                file_data = f.read()

            content_type = mimetypes.guess_type(original_filename or 'archivo.csv')[0] or 'text/csv'
            response = HttpResponse(file_data, content_type=content_type)
            safe_name = original_filename or "imported.csv"
            response['Content-Disposition'] = f'attachment; filename="{safe_name}"'
            return response
        else:
            messages.error(request, "No se encontró el archivo CSV original.")
            return redirect('surveys:results', public_id=public_id)

    # Caso 2: Encuesta nativa (Generar CSV)
    respuestas = (
        SurveyResponse.objects
        .filter(survey=survey)
        .prefetch_related('question_responses__question', 'question_responses__selected_option')
        .order_by('created_at')
    )

    if not respuestas.exists():
        messages.warning(request, "No hay respuestas para exportar.")
        return redirect('surveys:results', public_id=public_id)

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    filename = f"{survey.title.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')

    writer = csv.writer(response)
    preguntas = list(survey.questions.prefetch_related('options').all().order_by('order'))

    headers = ['ID_Respuesta', 'Fecha', 'Usuario'] + [p.text for p in preguntas]
    writer.writerow(headers)

    for respuesta in respuestas:
        row = [
            respuesta.id,
            respuesta.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            respuesta.user.username if respuesta.user else 'Anónimo',
        ]
        
        # Mapeo eficiente de respuestas
        resp_map = defaultdict(list)
        for qr in respuesta.question_responses.all():
            val = ''
            if qr.numeric_value is not None:
                val = str(qr.numeric_value)
            elif qr.selected_option and qr.selected_option.text:
                val = qr.selected_option.text
            elif qr.text_value:
                val = qr.text_value
            
            if val:
                resp_map[qr.question_id].append(val)

        for p in preguntas:
            row.append(" | ".join(resp_map[p.id]))

        writer.writerow(row)

    return response

# ============================================================
# VISTAS AUXILIARES Y API
# ============================================================

@login_required
def survey_analysis_ajax(request, public_id):
    try:
        survey = get_object_or_404(Survey, public_id=public_id)
        PermissionHelper.verify_survey_access(survey, request.user)
        
        respuestas_qs = SurveyResponse.objects.filter(survey=survey)
        analysis = SurveyAnalysisService.get_analysis_data(
            survey, respuestas_qs, include_charts=True, use_base_filter=True
        )
        
        return JsonResponse({
            'success': True,
            'analysis_data': analysis['analysis_data'],
        }, encoder=DjangoJSONEncoder)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def api_crosstab_view(request, public_id):
    try:
        survey = get_object_or_404(Survey, public_id=public_id)
        PermissionHelper.verify_survey_access(survey, request.user)
        
        row_id = request.GET.get('row')
        col_id = request.GET.get('col')
        
        if not row_id or not col_id:
            return JsonResponse({'error': 'Faltan parámetros row/col'}, status=400)

        # Nota: Asegúrate de tener implementado generate_crosstab en SurveyAnalysisService
        # Si no, esta función retornará error controlado.
        if hasattr(SurveyAnalysisService, 'generate_crosstab'):
            result = SurveyAnalysisService.generate_crosstab(survey, row_id, col_id)
            if not result:
                return JsonResponse({'error': 'No se pudieron generar datos'}, status=400)
            return JsonResponse(result)
        else:
            return JsonResponse({'error': 'Funcionalidad Crosstab no implementada en el servicio'}, status=501)
            
    except Exception as e:
        logger.error(f"Error generando crosstab para {public_id}: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def debug_analysis_view(request, public_id):
    try:
        survey = get_object_or_404(Survey.objects.prefetch_related('questions__options'), public_id=public_id)
    except Http404:
        return JsonResponse({'error': 'Encuesta no encontrada'}, status=404)
    
    PermissionHelper.verify_survey_access(survey, request.user)
    respuestas_qs = SurveyResponse.objects.filter(survey=survey)
    analysis = SurveyAnalysisService.get_analysis_data(survey, respuestas_qs, include_charts=True)

    summary = []
    for q in analysis.get('analysis_data', []):
        summary.append({
            'id': q.get('id'),
            'text': q.get('text'),
            'type': q.get('type'),
            'insight_present': bool(q.get('insight_data')),
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
        
        # Limpieza de caché relacionada si existe
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