"""
surveys/views/report_views.py
Vistas de reporte conectadas a tareas asíncronas (Celery).
"""
import json
import os
import csv
import mimetypes
from datetime import datetime
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse, Http404, FileResponse
from django.contrib import messages
from django.template.loader import render_to_string
from django.db.models import Q, Max
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django_ratelimit.decorators import ratelimit
from django.conf import settings
from django.urls import reverse

from surveys.models import Survey, SurveyResponse, QuestionResponse, ImportJob, Question
from core.models_reports import ReportJob
from core.utils.logging_utils import StructuredLogger
from core.utils.helpers import PermissionHelper, DateFilterHelper
from core.services.survey_analysis import SurveyAnalysisService
from surveys.tasks import generate_report_task
from core.reports.pdf_generator import DataNormalizer

logger = StructuredLogger('surveys')

CACHE_TIMEOUT_STATS = 300

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
        # Usamos prefetch o subquery optimizado gracias a los nuevos índices
        respuestas_ids = QuestionResponse.objects.filter(question=pregunta_filtro).filter(q_filter).values_list('survey_response_id', flat=True)
        respuestas_qs = respuestas_qs.filter(id__in=respuestas_ids)
    
    return respuestas_qs

def _process_crosstab_for_template(crosstab_raw):
    """Transforma el diccionario 'split' de Pandas a estructura para Template."""
    if not crosstab_raw or 'error' in crosstab_raw:
        return None, None

    data = crosstab_raw.get('data', {})
    columns = data.get('columns', [])
    index = data.get('index', [])
    values = data.get('data', [])

    if not columns or not index or not values:
        return None, None

    headers = columns[:-1] 
    formatted_rows = []
    
    for i, row_label in enumerate(index[:-1]):
        row_values = values[i]
        row_total = row_values[-1]
        
        cells = []
        for val in row_values[:-1]:
            percentage = 0
            if row_total > 0:
                percentage = round((val / row_total) * 100, 1)
            
            cells.append({
                'count': val,
                'percentage': percentage
            })
            
        formatted_rows.append({
            'label': row_label,
            'values': cells,
            'total': row_total
        })

    crosstab_data = {
        'row_label': crosstab_raw.get('row_label', 'Fila'),
        'col_label': crosstab_raw.get('col_label', 'Columna'),
        'headers': headers,
        'rows': formatted_rows
    }

    datasets = []
    for col_idx, col_name in enumerate(headers):
        col_data = [row[col_idx] for row in values[:-1]]
        datasets.append({
            'label': str(col_name),
            'data': col_data
        })

    crosstab_chart = {
        'labels': [str(l) for l in index[:-1]],
        'datasets': datasets
    }

    return crosstab_data, json.dumps(crosstab_chart, cls=DjangoJSONEncoder)


# ============================================================
# VISTAS PRINCIPALES
# ============================================================

@login_required
def survey_results_view(request, public_id):
    """Vista principal del Dashboard de Resultados."""
    try:
        # Optimizacion: select_related y prefetch_related
        survey = get_object_or_404(
            Survey.objects.select_related('author').prefetch_related('questions__options'),
            public_id=public_id
        )
    except Http404:
        return render(request, 'surveys/crud/not_found.html', {'survey_id': public_id}, status=404)
    
    PermissionHelper.verify_survey_access(survey, request.user)
    
    start = request.GET.get('start')
    end = request.GET.get('end')
    segment_col = request.GET.get('segment_col', '').strip()
    segment_val = request.GET.get('segment_val', '').strip()
    segment_demo = request.GET.get('segment_demo', '').strip()
    crosstab_col = request.GET.get('crosstab_col', '').strip()
    
    has_filters = bool(start or end or segment_col)
    
    respuestas_qs = SurveyResponse.objects.filter(survey=survey)
    
    if start or end:
        respuestas_qs, _ = DateFilterHelper.apply_filters(respuestas_qs, start, end)
        
    if segment_col:
        respuestas_qs = _apply_segment_filter(
            respuestas_qs, survey, segment_col, segment_val, segment_demo
        )

    # Llamada al servicio optimizado
    analysis_result = SurveyAnalysisService.get_analysis_data(
        survey,
        respuestas_qs,
        config={'tone': 'FORMAL', 'include_quotes': True}
    )

    insights_list = analysis_result.get('analysis_data', [])
    for item in insights_list:
        if 'chart' in item and item['chart']:
            if isinstance(item['chart'], str):
                item['chart_json'] = item['chart']
            else:
                item['chart_json'] = json.dumps(item['chart'], cls=DjangoJSONEncoder)

    kpi_score = analysis_result.get('kpi_prom_satisfaccion', 0)
    evolution = analysis_result.get('evolution', {})
    
    top_insights = [
        item for item in insights_list 
        if item.get('insight_data', {}).get('mood') in ['CRITICO', 'EXCELENTE']
    ][:3]

    crosstab_data = None
    crosstab_chart_json = None
    
    if crosstab_col:
        row_id = segment_col
        col_id = crosstab_col
        
        if not row_id:
             # Si no se seleccionó fila, intenta tomar la primera pregunta categórica que no sea la columna
             first_q = survey.questions.exclude(id=col_id).filter(type__in=['single', 'multi', 'select']).first()
             if first_q:
                 row_id = str(first_q.id)

        if row_id and col_id and row_id != col_id:
            # Nota: Esto requiere que SurveyAnalysisService.generate_crosstab esté implementado 
            # o que conectes el servicio antiguo.
            raw_crosstab = SurveyAnalysisService.generate_crosstab(
                survey, row_id, col_id, queryset=respuestas_qs
            )
            crosstab_data, crosstab_chart_json = _process_crosstab_for_template(raw_crosstab)

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
        'crosstab_data': crosstab_data,
        'crosstab_chart_json': crosstab_chart_json,
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
    """Vista AJAX para preview de reportes."""
    try:
        survey = get_object_or_404(Survey, public_id=public_id)
        PermissionHelper.verify_survey_access(survey, request.user)
        
        start = request.POST.get('start_date') or request.GET.get('start_date')
        end = request.POST.get('end_date') or request.GET.get('end_date')
        window = request.POST.get('window_days')
        
        respuestas_qs = SurveyResponse.objects.filter(survey=survey)
        
        if not start and window and window.isdigit():
            start_dt = timezone.now() - timedelta(days=int(window))
            respuestas_qs = respuestas_qs.filter(created_at__gte=start_dt)
        elif start or end:
            respuestas_qs, _ = DateFilterHelper.apply_filters(respuestas_qs, start, end)
        
        analysis = SurveyAnalysisService.get_analysis_data(
            survey, respuestas_qs, include_charts=True
        )
        
        for item in analysis.get('analysis_data', []):
            if 'chart' in item:
                item['chart_json'] = json.dumps(item['chart'], cls=DjangoJSONEncoder)
        
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
        messages.error(request, "Encuesta no encontrada.")
        return redirect('dashboard')

    if getattr(survey, 'is_imported', False):
        import_job = ImportJob.objects.filter(survey=survey, status="completed").order_by('-created_at').first()
        if import_job and import_job.csv_file and os.path.exists(import_job.csv_file.path):
            return FileResponse(open(import_job.csv_file.path, 'rb'), as_attachment=True, filename=import_job.original_filename or "data.csv")

    respuestas = SurveyResponse.objects.filter(survey=survey).order_by('created_at').prefetch_related('question_responses__question')
    
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    filename = f"{survey.title[:20]}_{datetime.now().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')

    writer = csv.writer(response)
    preguntas = list(survey.questions.all().order_by('order'))
    headers = ['ID', 'Fecha', 'Usuario'] + [p.text for p in preguntas]
    writer.writerow(headers)

    for r in respuestas:
        row = [r.id, r.created_at, r.user.username if r.user else 'Anon']
        q_map = {qr.question_id: (qr.text_value or str(qr.numeric_value or '')) for qr in r.question_responses.all()}
        for p in preguntas:
            row.append(q_map.get(p.id, ''))
        writer.writerow(row)

    return response


@login_required
def survey_analysis_ajax(request, public_id):
    """API para obtener datos JSON puros."""
    try:
        survey = get_object_or_404(Survey, public_id=public_id)
        PermissionHelper.verify_survey_access(survey, request.user)
        
        respuestas_qs = SurveyResponse.objects.filter(survey=survey)
        analysis = SurveyAnalysisService.get_analysis_data(survey, respuestas_qs, include_charts=True)
        
        return JsonResponse({'success': True, 'analysis_data': analysis['analysis_data']}, encoder=DjangoJSONEncoder)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def api_crosstab_view(request, public_id):
    """API dedicada para cargar cruces de variables vía AJAX."""
    try:
        survey = get_object_or_404(Survey, public_id=public_id)
        PermissionHelper.verify_survey_access(survey, request.user)
        
        row_id = request.GET.get('row')
        col_id = request.GET.get('col')
        
        if not row_id or not col_id:
            return JsonResponse({'error': 'Faltan parámetros row/col'}, status=400)

        raw_crosstab = SurveyAnalysisService.generate_crosstab(survey, row_id, col_id)
        if 'error' in raw_crosstab:
            return JsonResponse(raw_crosstab, status=400)
            
        crosstab_data, chart_json = _process_crosstab_for_template(raw_crosstab)
        
        return JsonResponse({
            'success': True,
            'crosstab_data': crosstab_data,
            'chart_json': json.loads(chart_json) if chart_json else {}
        })
            
    except Exception as e:
        logger.error(f"Error crosstab api: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def debug_analysis_view(request, public_id):
    """Vista de depuración."""
    survey = get_object_or_404(Survey, public_id=public_id)
    PermissionHelper.verify_survey_access(survey, request.user)
    
    analysis = SurveyAnalysisService.get_analysis_data(survey, SurveyResponse.objects.filter(survey=survey))
    return JsonResponse(analysis, encoder=DjangoJSONEncoder)

def survey_thanks_view(request):
    """Vista pública de agradecimiento."""
    return render(request, 'surveys/responses/thanks.html', {
        'status': request.GET.get('status', 'active'),
        'success': request.GET.get('success') == '1'
    })

@login_required
def change_survey_status(request, public_id):
    """Endpoint para cambiar estado (Active/Pause/Closed)."""
    if request.method != 'POST': return JsonResponse({'error': 'POST required'}, status=405)
    survey = get_object_or_404(Survey, public_id=public_id, author=request.user)
    try:
        data = json.loads(request.body)
        survey.status = data.get('status')
        survey.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# ============================================================
# 🚀 NUEVAS VISTAS ASÍNCRONAS PARA REPORTES (PDF/PPTX)
# ============================================================

@login_required
def report_pdf_view(request):
    """
    Inicia la generación del PDF en segundo plano (Celery).
    Retorna un JSON con el job_id para que el frontend haga polling.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido. Use POST.'}, status=405)

    survey_id = request.POST.get('public_id') or request.POST.get('survey_id')
    if not survey_id: return JsonResponse({'error': "Falta ID de encuesta"}, status=400)
    
    # Obtener Survey
    if str(survey_id).isdigit():
        survey = get_object_or_404(Survey, id=survey_id, author=request.user)
    else:
        survey = get_object_or_404(Survey, public_id=survey_id, author=request.user)
    
    try:
        # 1. Recopilar filtros del request
        filters = {
            'start_date': request.POST.get('start_date'),
            'end_date': request.POST.get('end_date'),
            'include_charts': request.POST.get('include_charts', 'off'),
            'include_table': request.POST.get('include_table', 'off'),
            'include_kpis': request.POST.get('include_kpis', 'off'),
            'window_days': request.POST.get('window_days')
        }

        # 2. Crear el registro del trabajo (Job)
        job = ReportJob.objects.create(
            user=request.user,
            survey=survey,
            report_type='PDF',
            status='PENDING',
            metadata={'filters': filters}
        )

        # 3. Lanzar la tarea a Celery
        generate_report_task.delay(job.id)

        # 4. Responder con éxito e ID
        return JsonResponse({
            'success': True,
            'job_id': job.id,
            'message': 'Generando reporte PDF en segundo plano...'
        })

    except Exception as e:
        logger.error(f"Error iniciando reporte PDF: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def report_powerpoint_view(request):
    """
    Inicia la generación del PowerPoint en segundo plano (Celery).
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    survey_id = request.POST.get('public_id') or request.POST.get('survey_id')
    if not survey_id: return JsonResponse({'error': "Falta ID de encuesta"}, status=400)

    if str(survey_id).isdigit():
        survey = get_object_or_404(Survey, id=survey_id, author=request.user)
    else:
        survey = get_object_or_404(Survey, public_id=survey_id, author=request.user)

    try:
        filters = {
            'start_date': request.POST.get('start_date'),
            'end_date': request.POST.get('end_date'),
            'include_charts': request.POST.get('include_charts', 'off'),
            'include_table': request.POST.get('include_table', 'off'),
        }

        job = ReportJob.objects.create(
            user=request.user,
            survey=survey,
            report_type='PPTX',
            status='PENDING',
            metadata={'filters': filters}
        )
        
        generate_report_task.delay(job.id)
        
        return JsonResponse({
            'success': True, 
            'job_id': job.id,
            'message': 'Generando presentación PPTX en segundo plano...'
        })

    except Exception as e:
        logger.error(f"Error iniciando reporte PPTX: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def check_report_status(request, job_id):
    """
    Endpoint de polling. El frontend llama aquí cada X segundos para ver si el reporte acabó.
    """
    job = get_object_or_404(ReportJob, id=job_id, user=request.user)
    
    data = {
        'status': job.status,
        'completed_at': job.completed_at,
        'url': None
    }
    
    if job.status == 'COMPLETED' and job.file_url:
        # Generamos una URL para la vista de descarga segura
        data['url'] = reverse('surveys:download_report', args=[job.id])
        
    elif job.status == 'FAILED':
        data['error'] = job.metadata.get('error', 'Error desconocido')

    return JsonResponse(data)

@login_required
def download_report_file(request, job_id):
    """
    Sirve el archivo final de forma segura.
    Verifica que el usuario sea el dueño del job.
    """
    job = get_object_or_404(ReportJob, id=job_id, user=request.user)
    
    if job.status != 'COMPLETED' or not job.file_path or not os.path.exists(job.file_path):
        raise Http404("El archivo no está disponible o el reporte falló.")

    # Servir el archivo usando FileResponse (eficiente para archivos binarios)
    filename = os.path.basename(job.file_path)
    return FileResponse(open(job.file_path, 'rb'), as_attachment=True, filename=filename)