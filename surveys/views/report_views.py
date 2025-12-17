"""
surveys/views/report_views.py
Optimized report views for survey results.
"""
import csv
import json
import os
from datetime import datetime


from django.contrib.auth.views import redirect_to_login
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse, Http404, FileResponse
from django.contrib import messages
from django.template.loader import render_to_string
from django.db.models import Q
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django_ratelimit.decorators import ratelimit
from asgiref.sync import sync_to_async

from django.contrib.auth.views import redirect_to_login

from surveys.models import Survey, SurveyResponse, QuestionResponse, ImportJob
from core.utils.logging_utils import StructuredLogger
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

def _process_crosstab_for_template(crosstab_raw):
    """
    Transforma el diccionario 'split' de Pandas (del servicio) 
    a la estructura amigable que espera el Template HTML.
    """
    if not crosstab_raw or 'error' in crosstab_raw:
        return None, None

    data = crosstab_raw.get('data', {})
    columns = data.get('columns', []) # Headers (Columna B) + "Total"
    index = data.get('index', [])     # Labels (Columna A) + "Total"
    values = data.get('data', [])     # Matriz de valores

    # Validación básica
    if not columns or not index or not values:
        return None, None

    # 1. Preparar Headers (Quitamos 'Total' para iterarlo aparte si queremos, o lo dejamos)
    # El template espera headers sin el "Total" final en la iteración principal
    headers = columns[:-1] 

    formatted_rows = []
    
    # 2. Iterar filas (excepto la última que es Total General)
    for i, row_label in enumerate(index[:-1]):
        row_values = values[i]
        row_total = row_values[-1] # El último valor es el total de la fila
        
        cells = []
        # Iterar celdas (excepto la última que es el total)
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

    # 3. Estructura final para HTML
    crosstab_data = {
        'row_label': crosstab_raw.get('row_label', 'Fila'),
        'col_label': crosstab_raw.get('col_label', 'Columna'),
        'headers': headers,
        'rows': formatted_rows
    }

    # 4. Estructura para Chart.js (Barras Apiladas)
    # Datasets: Una serie por cada COLUMNA (excepto total)
    datasets = []
    for col_idx, col_name in enumerate(headers):
        # Extraemos los datos de esta columna para todas las filas (menos la fila total)
        col_data = [row[col_idx] for row in values[:-1]]
        datasets.append({
            'label': str(col_name),
            'data': col_data
        })

    crosstab_chart = {
        'labels': [str(l) for l in index[:-1]], # Etiquetas del eje X (Filas)
        'datasets': datasets
    }

    return crosstab_data, json.dumps(crosstab_chart, cls=DjangoJSONEncoder)

# ============================================================
# VISTAS PRINCIPALES
# ============================================================

async def survey_results_view(request, public_id):
    """
    Vista principal del Dashboard de Resultados.
    Orquesta los datos del Service y los pasa al Template.
    """
    # Manual authentication check for async view
    is_authenticated = await sync_to_async(lambda: request.user.is_authenticated)()
    if not is_authenticated:
        return redirect_to_login(request.get_full_path())
    try:
        survey = await sync_to_async(get_object_or_404, thread_sensitive=True)(
            Survey.objects.select_related('author').prefetch_related('questions__options'),
            public_id=public_id
        )
    except Http404:
        render_async = sync_to_async(render, thread_sensitive=True)
        return await render_async(request, 'surveys/crud/not_found.html', {'survey_id': public_id}, status=404)
    await PermissionHelper.verify_survey_access(survey, request.user)

    # --- 1. Filtros ---
    start = request.GET.get('start')
    end = request.GET.get('end')
    segment_col = request.GET.get('segment_col', '').strip()
    segment_val = request.GET.get('segment_val', '').strip()
    segment_demo = request.GET.get('segment_demo', '').strip()
    crosstab_col = request.GET.get('crosstab_col', '').strip() # Nuevo Filtro

    has_filters = bool(start or end or segment_col)

    respuestas_qs = await sync_to_async(lambda: SurveyResponse.objects.filter(survey=survey), thread_sensitive=True)()

    if start or end:
        # DateFilterHelper.apply_filters may be async, so always await
        maybe_coroutine = sync_to_async(DateFilterHelper.apply_filters, thread_sensitive=True)(respuestas_qs, start, end)
        if hasattr(maybe_coroutine, '__await__'):
            respuestas_qs, _ = await maybe_coroutine
        else:
            respuestas_qs, _ = maybe_coroutine

    if segment_col:
        maybe_coroutine = sync_to_async(_apply_segment_filter, thread_sensitive=True)(
            respuestas_qs, survey, segment_col, segment_val, segment_demo
        )
        if hasattr(maybe_coroutine, '__await__'):
            respuestas_qs = await maybe_coroutine
        else:
            respuestas_qs = maybe_coroutine

    # --- 2. Obtener Análisis General ---
    cache_key = f"analysis_view_v17_{survey.id}_{start}_{end}_{segment_col}_{segment_val}"

    analysis_result = await SurveyAnalysisService.get_analysis_data(
        survey,
        respuestas_qs,
        config={'tone': 'FORMAL', 'include_quotes': True}
    )

    # Serializar Charts para el Template (asegura chart_json como string JSON)
    insights_list = analysis_result.get('analysis_data', [])
    for item in insights_list:
        if 'chart' in item and item['chart']:
            if isinstance(item['chart'], str):
                item['chart_json'] = item['chart']
            else:
                item['chart_json'] = json.dumps(item['chart'], cls=DjangoJSONEncoder)

    # Mapear correctamente el KPI de satisfacción
    kpi_score = analysis_result.get('kpi_prom_satisfaccion', 0)
    evolution = analysis_result.get('evolution', {})

    # Top Insights (Mood crítico o excelente)
    top_insights = [
        item for item in insights_list 
        if item.get('insight_data', {}).get('mood') in ['CRITICO', 'EXCELENTE']
    ][:3]

    # --- 3. Lógica de Tabla Cruzada (Crosstab) ---
    crosstab_data = None
    crosstab_chart_json = None

    if crosstab_col:
        row_id = segment_col
        col_id = crosstab_col

        if not row_id:
            first_q = await sync_to_async(lambda: survey.questions.exclude(id=col_id).filter(type__in=['single', 'multi', 'select']).first(), thread_sensitive=True)()
            if first_q:
                row_id = str(first_q.id)

        if row_id and col_id and row_id != col_id:
            raw_crosstab = await sync_to_async(SurveyAnalysisService.generate_crosstab, thread_sensitive=True)(
                survey, row_id, col_id, queryset=respuestas_qs
            )
            crosstab_data, crosstab_chart_json = await sync_to_async(_process_crosstab_for_template, thread_sensitive=True)(raw_crosstab)

    preguntas_filtro = await sync_to_async(lambda: list(
        survey.questions.values('id', 'text', 'type', 'is_demographic').order_by('order')
    ), thread_sensitive=True)()

    context = {
        'survey': survey,
        'total_respuestas': await sync_to_async(respuestas_qs.count, thread_sensitive=True)(),
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
        'has_date_fields': await sync_to_async(_has_date_fields, thread_sensitive=True)(survey.id),
        'top_insights': top_insights,
        'ignored_questions': analysis_result.get('ignored_questions', [])
    }
    render_async = sync_to_async(render, thread_sensitive=True)
    return await render_async(request, 'surveys/responses/results.html', context)


async def report_preview(request, public_id):
    """Vista AJAX para preview de reportes."""
    is_authenticated = await sync_to_async(lambda: request.user.is_authenticated)()
    if not is_authenticated:
        return redirect_to_login(request.get_full_path())
    try:
        survey = await sync_to_async(get_object_or_404, thread_sensitive=True)(Survey, public_id=public_id)
        await PermissionHelper.verify_survey_access(survey, request.user)
        start = request.POST.get('start_date') or request.GET.get('start_date')
        end = request.POST.get('end_date') or request.GET.get('end_date')
        window = request.POST.get('window_days')
        respuestas_qs = await sync_to_async(lambda: SurveyResponse.objects.filter(survey=survey), thread_sensitive=True)()
        if not start and window and window.isdigit():
            from django.utils import timezone
            from datetime import timedelta
            start_dt = timezone.now() - timedelta(days=int(window))
            respuestas_qs = await sync_to_async(lambda: respuestas_qs.filter(created_at__gte=start_dt), thread_sensitive=True)()
        elif start or end:
            respuestas_qs, _ = await sync_to_async(DateFilterHelper.apply_filters, thread_sensitive=True)(respuestas_qs, start, end)
        analysis = await SurveyAnalysisService.get_analysis_data(
            survey, respuestas_qs, include_charts=True
        )
        for item in analysis.get('analysis_data', []):
            if 'chart' in item:
                item['chart_json'] = json.dumps(item['chart'], cls=DjangoJSONEncoder)
        render_to_string_async = sync_to_async(render_to_string, thread_sensitive=True)
        html = await render_to_string_async('core/reports/_report_preview_content.html', {
            'survey': survey,
            'analysis': analysis,
            'kpi_score': analysis.get('kpi_score', 0),
            'generated_at': datetime.now()
        }, request=request)
        return JsonResponse({'success': True, 'html': html})
        
    except Exception as e:
        logger.exception(f"Error generando preview reporte: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@ratelimit(key='user', rate='10/h', method='GET', block=True)
async def export_survey_csv_view(request, public_id):
    """Exportar resultados de encuesta a CSV."""
    is_authenticated = await sync_to_async(lambda: request.user.is_authenticated)()
    if not is_authenticated:
        return redirect_to_login(request.get_full_path())
    try:
        survey = await sync_to_async(get_object_or_404, thread_sensitive=True)(Survey, public_id=public_id, author=request.user)
    except Http404:
        messages.error(request, "Encuesta no encontrada.")
        return redirect('dashboard')

    # Caso 1: Importada (Archivo original) — usar API de storage si es posible
    if getattr(survey, 'is_imported', False):
        import_job = await sync_to_async(lambda: ImportJob.objects.filter(survey=survey, status="completed").order_by('-created_at').first(), thread_sensitive=True)()
        import os
        if import_job and import_job.csv_file:
            # Intentar primero con el storage por si se usa S3 u otro backend
            try:
                from django.core.files.storage import default_storage
                if default_storage.exists(import_job.csv_file):
                    file_obj = default_storage.open(import_job.csv_file, 'rb')
                    return FileResponse(file_obj, as_attachment=True, filename=import_job.original_filename or 'data.csv', content_type='text/csv')
            except Exception:
                pass
            # Fallback a sistema de archivos local
            if os.path.exists(import_job.csv_file):
                return FileResponse(open(import_job.csv_file, 'rb'), as_attachment=True, filename=import_job.original_filename or 'data.csv', content_type='text/csv')

    # Caso 2: Nativa (Generar)
    respuestas = await sync_to_async(lambda: SurveyResponse.objects.filter(survey=survey).order_by('created_at').prefetch_related('question_responses__question'), thread_sensitive=True)()
    
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    filename = f"{survey.title[:20]}_{datetime.now().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')

    writer = csv.writer(response)
    preguntas = await sync_to_async(lambda: list(survey.questions.all().order_by('order')), thread_sensitive=True)()
    headers = ['ID', 'Fecha', 'Usuario'] + [p.text for p in preguntas]
    writer.writerow(headers)

    for r in respuestas:
        row = [r.id, r.created_at, r.user.username if r.user else 'Anon']
        q_map = {qr.question_id: (qr.text_value or str(qr.numeric_value or '')) for qr in r.question_responses.all()}
        for p in preguntas:
            row.append(q_map.get(p.id, ''))
        writer.writerow(row)

    return response

# ============================================================
# API ENDPOINTS
# ============================================================

async def survey_analysis_ajax(request, public_id):
    """API para obtener datos JSON puros (útil para recargar gráficas)."""
    try:
        survey = await sync_to_async(get_object_or_404, thread_sensitive=True)(Survey, public_id=public_id)
        await sync_to_async(PermissionHelper.verify_survey_access, thread_sensitive=True)(survey, request.user)
        respuestas_qs = await sync_to_async(lambda: SurveyResponse.objects.filter(survey=survey), thread_sensitive=True)()
        analysis = await sync_to_async(SurveyAnalysisService.get_analysis_data, thread_sensitive=True)(survey, respuestas_qs, include_charts=True)
        return JsonResponse({'success': True, 'analysis_data': analysis['analysis_data']}, encoder=DjangoJSONEncoder)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

async def api_crosstab_view(request, public_id):
    """API dedicada para cargar cruces de variables vía AJAX."""
    try:
        survey = await sync_to_async(get_object_or_404, thread_sensitive=True)(Survey, public_id=public_id)
        await sync_to_async(PermissionHelper.verify_survey_access, thread_sensitive=True)(survey, request.user)
        row_id = request.GET.get('row')
        col_id = request.GET.get('col')
        if not row_id or not col_id:
            return JsonResponse({'error': 'Faltan parámetros row/col'}, status=400)
        raw_crosstab = await sync_to_async(SurveyAnalysisService.generate_crosstab, thread_sensitive=True)(survey, row_id, col_id)
        if 'error' in raw_crosstab:
            return JsonResponse(raw_crosstab, status=400)
        crosstab_data, chart_json = await sync_to_async(_process_crosstab_for_template, thread_sensitive=True)(raw_crosstab)
        return JsonResponse({
            'success': True,
            'crosstab_data': crosstab_data,
            'chart_json': json.loads(chart_json) if chart_json else {}
        })
            
    except Exception as e:
        logger.error(f"Error crosstab api: {e}")
        return JsonResponse({'error': str(e)}, status=500)

async def debug_analysis_view(request, public_id):
    """Vista de depuración para verificar qué está viendo el sistema."""
    survey = await sync_to_async(get_object_or_404, thread_sensitive=True)(Survey, public_id=public_id)
    await sync_to_async(PermissionHelper.verify_survey_access, thread_sensitive=True)(survey, request.user)
    analysis = await SurveyAnalysisService.get_analysis_data(survey, await sync_to_async(lambda: SurveyResponse.objects.filter(survey=survey), thread_sensitive=True)())
    return JsonResponse(analysis, encoder=DjangoJSONEncoder)

async def survey_thanks_view(request):
    """Vista pública de agradecimiento."""
    render_async = sync_to_async(render, thread_sensitive=True)
    return await render_async(request, 'surveys/responses/thanks.html', {
        'status': request.GET.get('status', 'active'),
        'success': request.GET.get('success') == '1'
    })

async def change_survey_status(request, public_id):
    """Endpoint para cambiar estado (Active/Pause/Closed)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    survey = await sync_to_async(get_object_or_404, thread_sensitive=True)(Survey, public_id=public_id, author=request.user)
    try:
        data = json.loads(request.body)
        survey.status = data.get('status')
        await sync_to_async(survey.save, thread_sensitive=True)()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)