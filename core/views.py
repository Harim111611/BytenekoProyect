"""
core/views.py
Módulo de vistas principales para el dashboard, reportes y análisis.
"""
import json
from datetime import datetime, timedelta
from collections.abc import Mapping
from typing import Dict, Any, List, Optional, cast

from django.shortcuts import render, get_object_or_404
from asgiref.sync import sync_to_async, async_to_sync
from django.http import HttpResponse, Http404, JsonResponse, HttpRequest
from django.utils import timezone
from django.utils.text import slugify
from django.utils.dateparse import parse_date
from django.contrib.auth.views import redirect_to_login
from django.template.loader import render_to_string
from django.core.cache import cache
from django.conf import settings
from django.db.models import Count, Avg, Q, F, FloatField, ExpressionWrapper, Max
from django_ratelimit.decorators import ratelimit

from surveys.models import Survey, SurveyResponse, QuestionResponse, Question
from surveys.models_analytics import AnalysisSegment
from core.services.survey_analysis import SurveyAnalysisService
from core.reports.pdf_generator import PDFReportGenerator, DataNormalizer
from core.reports.pptx_generator import generate_full_pptx_report
from core.utils.helpers import ResponseDataBuilder
from core.utils.logging_utils import StructuredLogger

logger = StructuredLogger('core.views')

CACHE_TIMEOUT_DASHBOARD = 300
DEFAULT_CHART_DAYS = 14
ALERT_THRESHOLD_DAYS = 7
ALERT_PROGRESS_MIN = 30.0


def _is_truthy(value: object) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "on", "yes"}


def _redirect_to_login_if_needed(request: HttpRequest) -> HttpResponse | None:
    user = getattr(request, 'user', None)
    if not user or not getattr(user, 'is_authenticated', False):
        return redirect_to_login(request.get_full_path())
    return None


async def _redirect_to_login_if_needed_async(request: HttpRequest) -> HttpResponse | None:
    """Async-safe auth guard.

    Accessing request.user (SimpleLazyObject) can trigger DB work; do it in a
    thread via sync_to_async to avoid SynchronousOnlyOperation in async views.
    """
    is_authenticated = await sync_to_async(
        lambda: bool(getattr(getattr(request, 'user', None), 'is_authenticated', False)),
        thread_sensitive=True,
    )()
    if not is_authenticated:
        return redirect_to_login(request.get_full_path())
    return None


async def _get_authenticated_user_id_and_username(request: HttpRequest) -> tuple[int, str]:
    """Return (user_id, username) for an authenticated request, async-safe."""
    return await sync_to_async(
        lambda: (
            int(cast(Any, request.user).id),
            str(cast(Any, request.user).username),
        ),
        thread_sensitive=True,
    )()

def _get_filtered_responses(survey: Survey, data: Mapping[str, Any]):
    """Helper centralizado para filtros de fecha."""
    responses = survey.responses.all()
    window = data.get('window_days', 'all')
    
    if window == 'custom':
        start_str = data.get('start_date')
        end_str = data.get('end_date')
        if start_str:
            try:
                s_date = parse_date(start_str)
                if s_date: responses = responses.filter(created_at__date__gte=s_date)
            except ValueError: pass
        if end_str:
            try:
                e_date = parse_date(end_str)
                if e_date: responses = responses.filter(created_at__date__lte=e_date)
            except ValueError: pass
    
    elif window != 'all':
        try:
            days = int(window)
            start_date = timezone.now() - timedelta(days=days)
            responses = responses.filter(created_at__gte=start_date)
        except (ValueError, TypeError): pass
            
    return responses

# ==========================================
# DASHBOARD PRINCIPAL
# ==========================================

async def dashboard_view(request: HttpRequest) -> HttpResponse:
    redirect_response = await _redirect_to_login_if_needed_async(request)
    if redirect_response:
        return redirect_response

    user_id, username = await _get_authenticated_user_id_and_username(request)
    cache_key = f"dashboard_data_user_{user_id}"
    context = await sync_to_async(cache.get, thread_sensitive=True)(cache_key)

    if not context:
        logger.info(f"Generando dashboard cache para usuario {user_id}")
        user_surveys = await sync_to_async(lambda: Survey.objects.filter(author_id=user_id), thread_sensitive=True)()
        survey_stats = await sync_to_async(lambda: user_surveys.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status='active'))
        ), thread_sensitive=True)()
        total_surveys = survey_stats['total']
        active_count = survey_stats['active']

        responses_qs = await sync_to_async(lambda: SurveyResponse.objects.filter(survey__author_id=user_id).select_related('survey'), thread_sensitive=True)()
        total_responses = await sync_to_async(responses_qs.count, thread_sensitive=True)()
        today = timezone.now().date()
        responses_today = await sync_to_async(lambda: responses_qs.filter(created_at__date=today).count(), thread_sensitive=True)()
        interaction_rate = round((total_responses / total_surveys), 1) if total_surveys > 0 else 0

        kpis = [
            {'label': 'Encuestas Activas', 'value': active_count, 'icon': 'bi-broadcast', 'color': 'success', 'subtext': f'de {total_surveys} totales'},
            {'label': 'Respuestas Totales', 'value': total_responses, 'icon': 'bi-people-fill', 'color': 'primary', 'subtext': 'Histórico'},
            {'label': 'Recibidas Hoy', 'value': responses_today, 'icon': 'bi-bar-chart-fill', 'color': 'info', 'subtext': 'Interacciones hoy'},
            {'label': 'Carga por Encuesta', 'value': interaction_rate, 'icon': 'bi-arrow-repeat', 'color': 'dark', 'subtext': 'Respuestas promedio'},
        ]

        chart_labels, chart_data = await ResponseDataBuilder.get_daily_counts(responses_qs, days=DEFAULT_CHART_DAYS)
        pie_data = await ResponseDataBuilder.get_status_distribution(user_surveys)

        recent_activity_qs = await sync_to_async(lambda: list(user_surveys.annotate(response_count=Count('responses')).order_by('-updated_at')[:5]), thread_sensitive=True)()
        recent_activity = []
        for s in recent_activity_qs:
            goal = s.sample_goal if s.sample_goal > 0 else 1
            progress = int((s.response_count / goal) * 100)
            recent_activity.append({
                'id': s.id, 'public_id': s.public_id, 'title': s.title,
                'status': s.status, 'get_status_display': s.get_status_display(),
                'respuestas': s.response_count, 'objetivo': s.sample_goal,
                'progreso_pct': progress, 'visual_progress': min(progress, 100),
                'fecha': s.updated_at
            })

        alerts = await sync_to_async(_generate_performance_alerts_optimized, thread_sensitive=True)(user_surveys)

        context = {
            'page_name': 'dashboard', 'kpis': kpis,
            'chart_labels': json.dumps(chart_labels), 'chart_data': json.dumps(chart_data),
            'pie_data': json.dumps(pie_data), 'recent_activity': recent_activity,
            'alertas': alerts, 'user_name': username,
            'total_encuestas_count': total_surveys, 'total_respuestas_count': total_responses,
        }
        await sync_to_async(cache.set, thread_sensitive=True)(cache_key, context, CACHE_TIMEOUT_DASHBOARD)

    render_async = sync_to_async(render, thread_sensitive=True)
    return await render_async(request, 'core/dashboard/dashboard.html', context)

# ==========================================
# DASHBOARD DE RESULTADOS (ANALÍTICAS) - RESTAURADO
# ==========================================

async def dashboard_results_view(request: HttpRequest) -> HttpResponse:
    redirect_response = await _redirect_to_login_if_needed_async(request)
    if redirect_response:
        return redirect_response

    """
    Vista para el panel de analíticas globales.
    """
    filters = {
        'periodo': request.GET.get('periodo', '30')
    }
    user_id, _username = await _get_authenticated_user_id_and_username(request)
    summary_data = await _get_analytics_summary(user_id, filters)

    # Completar selects opcionales del template (evita listas vacías)
    try:
        analysis_segments = await sync_to_async(lambda: list(
            AnalysisSegment.objects.filter(user_id=user_id)
            .select_related('survey')
            .only('id', 'name', 'survey_id')
            .order_by('-created_at')[:50]
        ), thread_sensitive=True)()
    except Exception:
        analysis_segments = []

    try:
        latest_survey = await sync_to_async(lambda: Survey.objects.filter(author_id=user_id)
                                            .only('id', 'title')
                                            .order_by('-created_at')
                                            .first(), thread_sensitive=True)()
        if latest_survey:
            survey_questions = await sync_to_async(lambda: list(
                latest_survey.questions
                .filter(type__in=['single', 'multi', 'scale', 'select'])
                .values('id', 'text')
                .order_by('order')
            ), thread_sensitive=True)()
        else:
            survey_questions = []
        if not survey_questions:
            survey_questions = await sync_to_async(lambda: list(
                Question.objects.filter(
                    survey__author_id=user_id,
                    type__in=['single', 'multi', 'scale', 'select']
                ).values('id', 'text').order_by('survey_id', 'order')[:50]
            ), thread_sensitive=True)()
    except Exception:
        survey_questions = []

    summary_data['analysis_segments'] = analysis_segments
    summary_data['survey_questions'] = survey_questions
    
    # Contexto adicional para la plantilla
    summary_data['page_name'] = 'analytics'
    
    render_async = sync_to_async(render, thread_sensitive=True)
    return await render_async(request, 'core/dashboard/results_dashboard.html', summary_data)

async def global_results_pdf_view(request: HttpRequest) -> HttpResponse:
    redirect_response = await _redirect_to_login_if_needed_async(request)
    if redirect_response:
        return redirect_response

    """
    Genera un PDF con las analíticas globales.
    """
    filters = {
        'periodo': request.GET.get('periodo', '30')
    }
    user_id, _username = await _get_authenticated_user_id_and_username(request)
    data = await _get_analytics_summary(user_id, filters)
    
    pdf_file = await sync_to_async(PDFReportGenerator.generate_global_report, thread_sensitive=True)(data)
    
    if not pdf_file or not isinstance(pdf_file, (bytes, bytearray)) or not bytes(pdf_file).startswith(b"%PDF"):
        return HttpResponse("Error generando el reporte PDF o WeasyPrint no está configurado.", status=500)
    response = HttpResponse(pdf_file, content_type='application/pdf')
    filename = f"Global_Analytics_{datetime.now().strftime('%Y%m%d')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

# ==========================================
# REPORTES Y EXPORTACIÓN POR ENCUESTA
# ==========================================

async def reports_page_view(request: HttpRequest) -> HttpResponse:
    redirect_response = await _redirect_to_login_if_needed_async(request)
    if redirect_response:
        return redirect_response

    user_id, _username = await _get_authenticated_user_id_and_username(request)
    surveys = await sync_to_async(lambda: Survey.objects.filter(author_id=user_id).only('id', 'public_id', 'title', 'created_at', 'status').order_by('-created_at'), thread_sensitive=True)()
    render_async = sync_to_async(render, thread_sensitive=True)
    return await render_async(request, 'core/reports/reports_page.html', {'page_name': 'reports', 'surveys': surveys})

@ratelimit(key='user', rate='60/m', block=True)
def report_preview_ajax(request: HttpRequest, public_id: str) -> HttpResponse:
    """AJAX preview for reports.

    NOTE: This view is intentionally sync because django-ratelimit (v4.1.0)
    wraps views synchronously under WSGI.
    """
    redirect_response = _redirect_to_login_if_needed(request)
    if redirect_response:
        return redirect_response

    user_id = int(cast(Any, request.user).id)
    survey = get_object_or_404(Survey.objects.select_related('author'), public_id=public_id, author_id=user_id)
    try:
        responses_queryset = _get_filtered_responses(survey, request.GET)
        total_respuestas = responses_queryset.count()
        show_charts = _is_truthy(request.GET.get('include_charts'))
        show_kpis = _is_truthy(request.GET.get('include_kpis'))
        show_table = _is_truthy(request.GET.get('include_table'))

        analysis_result = async_to_sync(SurveyAnalysisService.get_analysis_data)(
            survey=survey,
            responses_queryset=responses_queryset,
            include_charts=show_charts,
        )

        nps_safe = analysis_result.get('nps_data', {})
        last_date = None
        if total_respuestas > 0:
            last_date = responses_queryset.aggregate(Max('created_at'))['created_at__max']

        completion_text = "N/A"
        if survey.sample_goal > 0:
            pct = int((total_respuestas / survey.sample_goal) * 100)
            completion_text = f"{pct}%"

        analysis_items = analysis_result.get('analysis_data', [])

        # Normalizar claves esperadas por el template
        for item in analysis_items or []:
            if 'total_responses' not in item and 'total_respuestas' in item:
                item['total_responses'] = item.get('total_respuestas', 0)
        options = {
            'include_kpis': show_kpis,
            'include_charts': show_charts,
            'include_table': show_table,
            'start_date': request.GET.get('start_date'),
            'end_date': request.GET.get('end_date'),
            'window_days': request.GET.get('window_days', 'all'),
            'total_responses': total_respuestas,
        }
        # Construir dict survey como en PDF (campos de contacto provienen del author)
        survey_dict = {
            'id': survey.id,
            'title': survey.title,
            'organization': getattr(getattr(survey, 'author', None), 'organization', '') or '',
            'address': getattr(getattr(survey, 'author', None), 'address', '') or '',
            'contact_email': getattr(getattr(survey, 'author', None), 'email', '') or '',
            'contact_website': getattr(getattr(survey, 'author', None), 'website', '') or '',
            'sections': [
                {
                    'id': 1,
                    'title': survey.title,
                    'subtitle': getattr(survey, 'description', '') or '',
                    'questions': [],
                }
            ],
            'offers': [],
        }

        # Enriquecer items como en PDF (imágenes base64 + metric_display)
        try:
            from core.reports.pdf_generator import add_static_chart_images
            add_static_chart_images(analysis_items, include_charts=show_charts)
        except Exception:
            logger.exception("No se pudo enriquecer el preview con gráficos estáticos")

        try:
            consolidated_rows = DataNormalizer.prepare_consolidated_rows(analysis_items or [])
            metric_by_text = {
                row.get('question'): row.get('metric_display')
                for row in consolidated_rows
                if row.get('question')
            }
            for item in analysis_items or []:
                q_text = item.get('text')
                if q_text and 'metric_display' not in item:
                    item['metric_display'] = metric_by_text.get(q_text)
        except Exception:
            logger.exception("No se pudo calcular metric_display para preview")

        context = {
            'survey': survey_dict,
            'generated_at': timezone.now(),
            'generated_by_name': (
                (request.user.get_full_name() or '').strip()
                if hasattr(request.user, 'get_full_name')
                else ''
            ) or getattr(request.user, 'username', ''),
            'company_name': getattr(settings, 'COMPANY_NAME', 'Byteneko SaaS'),

            # Documento compartido (preview + PDF)
            'analysis_items': analysis_items,
            'options': options,
            'kpi_score': analysis_result.get('kpi_prom_satisfaccion', 0),

            # Extras (si los necesitamos en el futuro)
            'total_respuestas': total_respuestas,
            'last_response_date': last_date,
            'completion_rate': completion_text,
            'analysis_data': analysis_items,
            'kpi_prom_satisfaccion': analysis_result.get('kpi_prom_satisfaccion', 0),
            'nps_score': nps_safe.get('score'),
            'nps_chart_image': nps_safe.get('chart_image'),
            'heatmap_image': analysis_result.get('heatmap_image'),
            'include_kpis': show_kpis,
            'include_charts': show_charts,
            'include_table': show_table,
            'is_pdf': False,
            'consolidated_table_rows_limited': DataNormalizer.prepare_consolidated_rows(analysis_items)[:20],
            'consolidated_table_rows': DataNormalizer.prepare_consolidated_rows(analysis_items),
        }

        html = render_to_string('core/reports/_report_preview_content.html', context)
        return JsonResponse({'html': html, 'success': True})
    except Exception as e:
        logger.error(f"Error preview survey {public_id}: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e), 'success': False}, status=500)

async def report_pdf_view(request: HttpRequest) -> HttpResponse:
    redirect_response = await _redirect_to_login_if_needed_async(request)
    if redirect_response:
        return redirect_response

    user_id, _username = await _get_authenticated_user_id_and_username(request)

    survey_id = request.POST.get('public_id') or request.GET.get('survey_id')
    if not survey_id:
        raise Http404("Survey ID required")
    if str(survey_id).isdigit():
        survey = await sync_to_async(get_object_or_404, thread_sensitive=True)(
            Survey.objects.select_related('author'),
            id=survey_id,
            author_id=user_id,
        )
    else:
        survey = await sync_to_async(get_object_or_404, thread_sensitive=True)(
            Survey.objects.select_related('author'),
            public_id=survey_id,
            author_id=user_id,
        )
    try:
        responses_queryset = await sync_to_async(_get_filtered_responses, thread_sensitive=True)(survey, request.POST)
        include_charts = _is_truthy(request.POST.get('include_charts'))
        include_table = _is_truthy(request.POST.get('include_table'))
        include_kpis = _is_truthy(request.POST.get('include_kpis'))
        data = await SurveyAnalysisService.get_analysis_data(
            survey=survey,
            responses_queryset=responses_queryset,
            include_charts=include_charts,
        )

        analysis_items = data.get('analysis_data', [])
        consolidated_rows = DataNormalizer.prepare_consolidated_rows(analysis_items)
        metric_by_question_text = {row.get('question'): row.get('metric_display') for row in consolidated_rows if row.get('question')}

        # Construir dict survey para el template
        survey_dict = {
            'title': survey.title,
            'organization': getattr(survey.author, 'organization', ''),
            'address': getattr(survey.author, 'address', ''),
            'contact_email': getattr(survey.author, 'email', ''),
            'contact_website': getattr(survey.author, 'website', ''),
            'sections': [],
            'offers': [],
        }
        # Agrupar preguntas por sección si existe, si no, una sola sección
        # (IMPORTANTE: en vista async, toda consulta ORM debe ir vía sync_to_async)
        questions = await sync_to_async(
            lambda: list(survey.questions.order_by('order').values('id', 'text')),
            thread_sensitive=True,
        )()
        section = {
            'id': 1,
            'title': survey.title,
            'subtitle': survey.description or '',
            'questions': []
        }
        for q in questions:
            # Resumen "humano" del análisis (promedio/top topic/top opción, etc.)
            answer = metric_by_question_text.get(q.get('text'))
            section['questions'].append({
                'id': q.get('id'),
                'text': q.get('text'),
                'response': answer or '',
            })
        survey_dict['sections'].append(section)

        # Opcional: agregar ofertas si existen en el análisis
        if 'offers' in data:
            survey_dict['offers'] = data['offers']

        pdf_file = await sync_to_async(PDFReportGenerator.generate_report, thread_sensitive=True)(
            survey=survey_dict,
            analysis_data=analysis_items,
            nps_data=data.get('nps_data', {}),
            start_date=request.POST.get('start_date'),
            end_date=request.POST.get('end_date'),
            total_responses=await sync_to_async(responses_queryset.count, thread_sensitive=True)(),
            kpi_satisfaction_avg=data.get('kpi_prom_satisfaccion', 0),
            heatmap_image=data.get('heatmap_image'),
            include_table=include_table,
            include_kpis=include_kpis,
            include_charts=include_charts,
            request=request
        )

        if not pdf_file or not isinstance(pdf_file, (bytes, bytearray)) or not bytes(pdf_file).startswith(b"%PDF"):
            logger.error(
                "PDF generator returned invalid output",
                extra={
                    "survey_id": getattr(survey, "id", None),
                    "include_charts": include_charts,
                    "include_table": include_table,
                    "include_kpis": include_kpis,
                    "bytes_len": len(pdf_file) if isinstance(pdf_file, (bytes, bytearray)) else None,
                },
            )
            return HttpResponse(
                "Error generando el PDF. Revisa los logs del servidor para ver la excepción de WeasyPrint/plantilla.",
                status=500,
                content_type="text/plain; charset=utf-8",
            )

        response = HttpResponse(pdf_file, content_type='application/pdf')
        safe_title = slugify(survey.title)[:50]
        filename = f"Report_{safe_title}_{datetime.now().strftime('%Y%m%d')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        logger.error(f"Error generando PDF: {str(e)}", exc_info=True)
        return HttpResponse(f"Error: {str(e)}", status=500, content_type="text/plain; charset=utf-8")

async def report_powerpoint_view(request: HttpRequest) -> HttpResponse:
    redirect_response = await _redirect_to_login_if_needed_async(request)
    if redirect_response:
        return redirect_response

    user_id, _username = await _get_authenticated_user_id_and_username(request)

    survey_id = request.POST.get('public_id') or request.GET.get('survey_id')
    if not survey_id:
        raise Http404("Survey ID required")
    if str(survey_id).isdigit():
        survey = await sync_to_async(get_object_or_404, thread_sensitive=True)(Survey, id=survey_id, author_id=user_id)
    else:
        survey = await sync_to_async(get_object_or_404, thread_sensitive=True)(Survey, public_id=survey_id, author_id=user_id)
    try:
        responses_queryset = await sync_to_async(_get_filtered_responses, thread_sensitive=True)(survey, request.POST)
        include_charts = _is_truthy(request.POST.get('include_charts'))
        include_table = _is_truthy(request.POST.get('include_table'))
        include_kpis = _is_truthy(request.POST.get('include_kpis'))
        data = await SurveyAnalysisService.get_analysis_data(
            survey=survey,
            responses_queryset=responses_queryset,
            include_charts=include_charts,
        )
        pptx_file = await sync_to_async(generate_full_pptx_report, thread_sensitive=True)(
            survey=survey,
            analysis_data=data.get('analysis_data', []),
            nps_data=data.get('nps_data', {}),
            start_date=request.POST.get('start_date'),
            end_date=request.POST.get('end_date'),
            total_responses=await sync_to_async(responses_queryset.count, thread_sensitive=True)(),
            kpi_satisfaction_avg=data.get('kpi_prom_satisfaccion', 0),
            heatmap_image=data.get('heatmap_image'),
            include_table=include_table,
            include_kpis=include_kpis,
            include_charts=include_charts,
        )
        response = HttpResponse(pptx_file, content_type='application/vnd.openxmlformats-officedocument.presentationml.presentation')
        safe_title = slugify(survey.title)[:50]
        response['Content-Disposition'] = f'attachment; filename="Report_{safe_title}.pptx"'
        return response
    except Exception as e:
        logger.error(f"Error PPTX: {str(e)}", exc_info=True)
        return HttpResponse("Error generando PowerPoint.", status=500)

async def settings_view(request: HttpRequest) -> HttpResponse:
    redirect_response = await _redirect_to_login_if_needed_async(request)
    if redirect_response:
        return redirect_response

    render_async = sync_to_async(render, thread_sensitive=True)
    return await render_async(request, 'core/dashboard/settings.html', {'page_name': 'configuracion', 'user': request.user})

# ==========================================
# HELPERS PRIVADOS
# ==========================================

def _generate_performance_alerts_optimized(user_surveys) -> List[Dict[str, Any]]:
    seven_days_ago = timezone.now() - timedelta(days=ALERT_THRESHOLD_DAYS)
    alerts_qs = user_surveys.filter(
        status='active', created_at__lt=seven_days_ago, sample_goal__gt=0
    ).annotate(resp_count=Count('responses')).annotate(
        progress_pct=ExpressionWrapper(F('resp_count') * 100.0 / F('sample_goal'), output_field=FloatField())
    ).filter(progress_pct__lt=ALERT_PROGRESS_MIN).select_related().order_by('-updated_at')[:5]

    alerts = []
    for s in alerts_qs:
        alerts.append({
            'id': s.id, 'title': s.title, 'type': 'warning',
            'message': f'Bajo rendimiento: {int(s.progress_pct)}% del objetivo.', 'date': s.updated_at
        })
    return alerts

async def _get_analytics_summary(user_id: int, filters: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Calcula TODAS las métricas analíticas. Helper para dashboard_results_view y global_results_pdf_view.
    """
    if filters is None:
        filters = {}

    surveys = Survey.objects.filter(author_id=user_id)
    responses_qs = SurveyResponse.objects.filter(survey__author_id=user_id)
    
    periodo = filters.get('periodo', '30')
    if periodo != 'all':
        try:
            days = int(periodo)
            start_date = timezone.now() - timedelta(days=days)
            responses_qs = responses_qs.filter(created_at__gte=start_date)
        except (ValueError, TypeError):
            pass

    # Métricas Totales
    total_surveys = await sync_to_async(surveys.count, thread_sensitive=True)()
    total_active = await sync_to_async(lambda: surveys.filter(status='active').count(), thread_sensitive=True)()
    total_responses = await sync_to_async(responses_qs.count, thread_sensitive=True)()

    # Cambio Semanal
    now = timezone.now()
    week_start = now - timedelta(days=7)
    prev_week_start = now - timedelta(days=14)
    
    this_week_c = await sync_to_async(lambda: responses_qs.filter(created_at__gte=week_start).count(), thread_sensitive=True)()
    last_week_c = await sync_to_async(lambda: responses_qs.filter(created_at__gte=prev_week_start, created_at__lt=week_start).count(), thread_sensitive=True)()

    weekly_change = 0
    if last_week_c > 0:
        weekly_change = ((this_week_c - last_week_c) / last_week_c) * 100
    elif this_week_c > 0:
        weekly_change = 100

    # NPS Global Simplificado
    nps_stats = await sync_to_async(lambda: QuestionResponse.objects.filter(
        survey_response__in=responses_qs,
        question__type='scale'
    ).aggregate(
        total=Count('id'),
        promoters=Count('id', filter=Q(numeric_value__gte=9)),
        passives=Count('id', filter=Q(numeric_value__in=[7, 8])),
        detractors=Count('id', filter=Q(numeric_value__lte=6)),
        avg_satisfaction=Avg('numeric_value')
    ), thread_sensitive=True)()
    total_nps = nps_stats['total'] or 0
    nps_score = 0
    prom_pct, pass_pct, det_pct = 0, 0, 0
    if total_nps > 0:
        prom_pct = round((nps_stats['promoters'] / total_nps) * 100, 1)
        pass_pct = round((nps_stats['passives'] / total_nps) * 100, 1)
        det_pct = round((nps_stats['detractors'] / total_nps) * 100, 1)
        nps_score = round(prom_pct - det_pct, 0)

    global_satisfaction = nps_stats['avg_satisfaction'] or 0

    # Gráficas
    chart_labels, chart_data = await ResponseDataBuilder.get_daily_counts(responses_qs, days=30)

    # Categoría
    status_dist = await sync_to_async(lambda: list(surveys.values('status').annotate(count=Count('id'))), thread_sensitive=True)()
    status_map = dict(Survey.STATUS_CHOICES)
    cat_labels = [status_map.get(x['status'], x['status']) for x in status_dist]
    cat_data = [x['count'] for x in status_dist]

    # Weekly trend
    weekly_trend_data = []
    for i in range(4):
        s_date = now - timedelta(weeks=i+1)
        e_date = now - timedelta(weeks=i)
        c = await sync_to_async(
            lambda s=s_date, e=e_date: responses_qs.filter(created_at__range=(s, e)).count(),
            thread_sensitive=True,
        )()
        weekly_trend_data.insert(0, c)

    # Tops
    top_surveys = await sync_to_async(lambda: list(surveys.annotate(response_count=Count('responses')).order_by('-response_count')[:5]), thread_sensitive=True)()
    top_preguntas = await sync_to_async(lambda: list(Question.objects.filter(
        survey__in=surveys, 
        type='scale',
        questionresponse__isnull=False
    ).annotate(
        avg_score=Avg('questionresponse__numeric_value'),
        num_responses=Count('questionresponse')
    ).filter(
        num_responses__gte=1
    ).select_related('survey').order_by('-avg_score')[:10]), thread_sensitive=True)()

    return {
        'total_surveys': total_surveys,
        'total_active': total_active,
        'total_responses': total_responses,
        'weekly_change': weekly_change,
        'global_satisfaction': global_satisfaction,
        'global_nps': nps_score,
        'promoters': prom_pct,
        'passives': pass_pct,
        'detractors': det_pct,
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
        'categoria_labels': json.dumps(cat_labels),
        'categoria_data': json.dumps(cat_data),
        'weekly_trend': json.dumps(weekly_trend_data),
        'top_surveys': top_surveys,
        'top_preguntas': top_preguntas,
        'periodo': periodo
    }