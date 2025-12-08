# core/views.py
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, Http404
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.template.loader import render_to_string
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Count, Avg
from django_ratelimit.decorators import ratelimit
from datetime import datetime, timedelta
import json

from surveys.models import Survey, SurveyResponse, QuestionResponse
from core.services.survey_analysis import SurveyAnalysisService
from core.reports.pdf_generator import PDFReportGenerator
from core.reports.pptx_generator import PPTXReportGenerator
from core.validators import DateFilterValidator, SurveyValidator
from core.utils.helpers import DateFilterHelper, ResponseDataBuilder, PermissionHelper
from core.utils.logging_utils import StructuredLogger

# Configure logger
logger = StructuredLogger('core')


# ============================================================
# 1. MAIN DASHBOARD
# ============================================================
@login_required
def dashboard_view(request):
    user = request.user
    cache_key = f"dashboard_data_user_{user.id}"
    context = cache.get(cache_key)

    if not context:
        user_surveys = Survey.objects.filter(author=user)
        total_surveys = user_surveys.count()
        active_count = user_surveys.filter(status='active').count()
        responses_qs = SurveyResponse.objects.filter(survey__author=user).select_related('survey')
        total_responses = responses_qs.count()
        today = timezone.now().date()
        responses_today = responses_qs.filter(created_at__date=today).count()

        # Operational Widgets
        interaction_rate = round((total_responses / total_surveys), 1) if total_surveys > 0 else 0

        kpis = [
            {'label': 'Encuestas Activas', 'value': active_count, 'icon': 'bi-broadcast', 'color': 'success', 'subtext': f'de {total_surveys} totales'},
            {'label': 'Respuestas Totales', 'value': total_responses, 'icon': 'bi-people-fill', 'color': 'primary', 'subtext': 'Histórico'},
            {'label': 'Recibidas Hoy', 'value': responses_today, 'icon': 'bi-bar-chart-fill', 'color': 'info', 'subtext': 'Interacciones hoy'},
            {'label': 'Carga por Encuesta', 'value': interaction_rate, 'icon': 'bi-arrow-repeat', 'color': 'dark', 'subtext': 'Respuestas promedio'},
        ]

        # Helper for chart data
        chart_labels, chart_data = ResponseDataBuilder.get_daily_counts(responses_qs, days=14)
        pie_data = ResponseDataBuilder.get_status_distribution(user_surveys)

        recent_activity = []
        for s in user_surveys.annotate(response_count=Count('responses')).order_by('-updated_at')[:5]:
            resp_count = s.response_count
            goal = s.sample_goal if s.sample_goal > 0 else 1
            progress = int((resp_count / goal) * 100)
            recent_activity.append({
                'id': s.id,
                'public_id': s.public_id,
                'titulo': s.title,
                'title': s.title,
                'estado': s.status,
                'status': s.status,
                'get_estado_display': s.get_status_display(),
                'respuestas': resp_count, 'objetivo': s.sample_goal, 'progreso_pct': progress,
                'visual_progress': min(progress, 100), 'fecha': s.updated_at
            })
        
        alerts = []
        seven_days_ago = timezone.now() - timedelta(days=7)
        
        # Low performance active surveys
        for s in user_surveys.filter(status='active').annotate(response_count=Count('responses')):
            if s.sample_goal > 0:
                progress = (s.response_count / s.sample_goal) * 100
                if progress < 30 and s.created_at < seven_days_ago:
                    alerts.append({
                        'id': s.id,
                        'public_id': s.public_id,
                        'titulo': s.title,
                        'estado': s.status,
                        'tipo': 'bajo_rendimiento',
                        'icon': 'bi-exclamation-triangle-fill',
                        'color': 'warning',
                        'mensaje': f'Solo {s.response_count} de {s.sample_goal} respuestas ({int(progress)}%)',
                        'respuestas': s.response_count,
                        'fecha': s.updated_at
                    })
        
        # Sort alerts
        alerts = sorted(alerts, key=lambda x: x['fecha'], reverse=True)[:5]

        context = {
            'page_name': 'dashboard',
            'kpis': kpis,
            'chart_labels': json.dumps(chart_labels),
            'chart_data': json.dumps(chart_data),
            'pie_data': json.dumps(pie_data),
            'recent_activity': recent_activity,
            'alertas': alerts,
            'user_name': request.user.username,
            'total_encuestas_count': total_surveys,
            'total_respuestas_count': total_responses,
        }
        cache.set(cache_key, context, 300)

    return render(request, 'core/dashboard/dashboard.html', context)

@login_required
def dashboard_results_view(request):
    """GLOBAL Results Dashboard View."""
    user = request.user
    
    # Filtros de fecha y periodo
    start = request.GET.get('start')
    end = request.GET.get('end')
    period = request.GET.get('periodo', '30')
    days = None
    custom_range = False
    
    if start and end:
        try:
            start_date = timezone.make_aware(datetime.strptime(start, '%Y-%m-%d'))
            end_date = timezone.make_aware(datetime.strptime(end, '%Y-%m-%d'))
            custom_range = True
        except Exception:
            start_date = end_date = None

    user_surveys = Survey.objects.filter(author=user).select_related('author')
    responses_qs = SurveyResponse.objects.filter(survey__author=user).select_related('survey')

    if custom_range and start_date and end_date:
        responses_qs = responses_qs.filter(created_at__date__gte=start_date.date(), created_at__date__lte=end_date.date())
    else:
        if period != 'all':
            try:
                days = int(period)
                start_date = timezone.now() - timedelta(days=days)
                responses_qs = responses_qs.filter(created_at__gte=start_date)
            except ValueError:
                pass

    total_responses = responses_qs.count()
    total_surveys = user_surveys.count()
    total_active = user_surveys.filter(status='active').count()

    # Global Satisfaction
    satisfaction_avg = QuestionResponse.objects.filter(
        survey_response__survey__author=user,
        question__type='scale',
        numeric_value__isnull=False
    ).aggregate(avg=Avg('numeric_value'))['avg'] or 0

    # Calculate Global NPS
    nps_responses = QuestionResponse.objects.filter(
        survey_response__survey__author=user,
        question__type='scale',
        question__text__icontains='recomendar',
        numeric_value__isnull=False
    )
    
    total_nps = nps_responses.count()
    if total_nps > 0:
        promoters_count = nps_responses.filter(numeric_value__gte=9).count()
        detractors_count = nps_responses.filter(numeric_value__lte=6).count()
        passives_count = total_nps - promoters_count - detractors_count
        
        promoters = round((promoters_count / total_nps) * 100, 1)
        detractors = round((detractors_count / total_nps) * 100, 1)
        passives = round((passives_count / total_nps) * 100, 1)
        global_nps = round(promoters - detractors, 1)
    else:
        promoters = detractors = passives = global_nps = None

    # Chart Data
    chart_labels, chart_data = ResponseDataBuilder.get_daily_counts(responses_qs, days=30)
    
    # Top Surveys & Questions
    top_surveys = user_surveys.annotate(response_count=Count('responses')).order_by('-response_count')[:5]
    
    status_counts = user_surveys.values('status').annotate(count=Count('id')).order_by('-count')
    status_names = {'draft': 'Borrador', 'active': 'Activas', 'closed': 'Cerradas', 'archived': 'Archivadas'}
    category_labels = [status_names.get(e['status'], e['status']) for e in status_counts]
    category_data = [e['count'] for e in status_counts]
    
    from surveys.models import Question
    top_questions = Question.objects.filter(survey__author=user, type='scale').annotate(
        avg_score=Avg('questionresponse__numeric_value'),
        num_responses=Count('questionresponse')
    ).filter(num_responses__gte=5).order_by('-avg_score')[:10]
    
    # Weekly Trend
    weeks_data = []
    today = timezone.now().date()
    for i in range(3, -1, -1):
        week_start = today - timedelta(days=(i+1)*7)
        week_end = today - timedelta(days=i*7)
        week_count = responses_qs.filter(created_at__date__gte=week_start, created_at__date__lt=week_end).count()
        weeks_data.append(week_count)
    
    weekly_change = round(((weeks_data[-1] - weeks_data[-2]) / weeks_data[-2]) * 100, 1) if len(weeks_data) >= 2 and weeks_data[-2] > 0 else 0

    context = {
        'total_responses': total_responses,
        'total_surveys': total_surveys,
        'total_active': total_active,
        'global_satisfaction': satisfaction_avg,
        'global_nps': global_nps,
        'promoters': promoters,
        'passives': passives,
        'detractors': detractors,
        'weekly_change': weekly_change,
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
        'categoria_labels': json.dumps(category_labels),
        'categoria_data': json.dumps(category_data),
        'weekly_trend': json.dumps(weeks_data),
        'top_surveys': top_surveys,
        'top_preguntas': top_questions,
        'periodo': period,
    }
    return render(request, 'core/dashboard/results_dashboard.html', context)


@login_required
@ratelimit(key='user', rate='10/h', method='GET', block=True)
def global_results_pdf_view(request):
    """View to generate Global Results PDF using WeasyPrint."""
    try:
        from weasyprint import HTML
    except ImportError:
        return HttpResponse("WeasyPrint is not installed", status=500)
    
    user = request.user
    user_surveys = Survey.objects.filter(author=user)
    responses_qs = SurveyResponse.objects.filter(survey__author=user).select_related('survey')

    total_responses = responses_qs.count()
    total_surveys = user_surveys.count()
    total_active = user_surveys.filter(status='active').count()

    satisfaction_avg = QuestionResponse.objects.filter(
        survey_response__survey__author=user,
        question__type='scale',
        numeric_value__isnull=False
    ).aggregate(avg=Avg('numeric_value'))['avg'] or 0

    # Calculate Global NPS
    nps_responses = QuestionResponse.objects.filter(
        survey_response__survey__author=user,
        question__type='scale',
        question__text__icontains='recomendar',
        numeric_value__isnull=False
    )
    
    # ... (Cálculos de NPS y KPIs similares a dashboard_results_view) ...
    # Simplificado para brevedad, asumiendo la misma lógica que dashboard_results_view
    
    html_string = render_to_string('core/reports/_global_results_pdf.html', {
        'total_responses': total_responses,
        'total_surveys': total_surveys,
        'global_satisfaction': satisfaction_avg,
        'fecha_generacion': datetime.now().strftime('%d/%m/%Y %H:%M'),
        # Añadir resto del contexto necesario
    })
    
    html = HTML(string=html_string)
    pdf_file = html.write_pdf()

    response = HttpResponse(pdf_file, content_type='application/pdf')
    filename = f'resultados-globales-{datetime.now().strftime("%Y-%m-%d")}.pdf'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response


# ============================================================
# DATE FILTER UTILITIES
# ============================================================
def apply_date_filters(queryset, start=None, end=None, window=None):
    return DateFilterHelper.apply_filters(queryset, start, end, window)


# ============================================================
# REPORT VIEWS
# ============================================================

@login_required
def reports_page_view(request):
    """View for the main reports page."""
    surveys = Survey.objects.filter(author=request.user).order_by('-created_at')
    context = {'page_name': 'reports', 'surveys': surveys}
    return render(request, 'core/reports/reports_page.html', context)


@login_required
def report_preview_ajax(request, public_id):
    """
    AJAX endpoint que devuelve el HTML usado en la vista previa del reporte.
    """
    identifier_for_log = public_id

    try:
        # 1. Flags
        show_kpis = SurveyValidator.validate_boolean_param(request.GET.get("include_kpis", "true"), "include_kpis")
        show_charts = SurveyValidator.validate_boolean_param(request.GET.get("include_charts", "true"), "include_charts")
        show_table = SurveyValidator.validate_boolean_param(request.GET.get("include_table", "true"), "include_table")

        # 2. Filtros
        start = request.GET.get("start_date") or None
        end = request.GET.get("end_date") or None
        window = request.GET.get("window_days") or None

        if start: DateFilterValidator.validate_date_string(start, "start_date")
        if end: DateFilterValidator.validate_date_string(end, "end_date")
        if window and window != "all": DateFilterValidator.validate_window_days(window)

        # 3. Cargar encuesta
        try:
            survey = get_object_or_404(Survey.objects.prefetch_related("questions__options"), public_id=public_id)
            identifier_for_log = survey.public_id
        except Http404:
            logger.warning(f"Encuesta no encontrada: {public_id}")
            return HttpResponse(json.dumps({"error": "Encuesta no encontrada"}), content_type="application/json", status=404)

        PermissionHelper.verify_survey_access(survey, request.user)

        # 4. Datos
        qs = SurveyResponse.objects.filter(survey=survey).select_related("survey")
        qs, normalized_start = apply_date_filters(qs, start, end, window)
        
        cache_key = f"survey_analysis_{survey.id}_{normalized_start or 'all'}_{end or 'all'}_{window or 'all'}"
        data_pack = SurveyAnalysisService.get_analysis_data(survey, qs, include_charts=True, cache_key=cache_key)
        
        analysis_data = data_pack.get("analysis_data", []) or []
        
        # 5. Render
        html = render_to_string("core/reports/_report_preview_content.html", {
            "survey": survey,
            "analysis_data": analysis_data,
            "total_respuestas": qs.count(),
            "nps_score": data_pack.get("nps_data", {}).get("score"),
            "kpi_prom_satisfaccion": data_pack.get("kpi_prom_satisfaccion"),
            "include_kpis": show_kpis,
            "include_charts": show_charts,
            "include_table": show_table,
            "is_pdf": False,
            # Añadir filas consolidadas si es necesario para la tabla
            "consolidated_table_rows_limited": PDFReportGenerator.prepare_consolidated_rows(analysis_data)[:40]
        })

        return HttpResponse(html)

    except Exception as e:
        logger.error(f"[REPORT][PREVIEW][UNEXPECTED] encuesta={identifier_for_log} error={e}", exc_info=True)
        return HttpResponse(f"Error: {str(e)}", status=500)


def report_powerpoint_view(request):
    """View to generate and download PowerPoint report."""
    if request.method != 'POST':
        return HttpResponse("Method not allowed.", status=405)

    try:
        raw_identifier = request.POST.get('survey_id')
        # ... lógica de obtención de encuesta ...
        identifier = SurveyValidator.validate_survey_id(raw_identifier)
        lookup = {'public_id': identifier} if isinstance(identifier, str) else {'pk': identifier}
        
        survey = get_object_or_404(Survey, **lookup)
        PermissionHelper.verify_survey_access(survey, request.user)
        
        qs = SurveyResponse.objects.filter(survey=survey)
        # ... aplicar filtros de fecha ...
        
        # Mock de generación para completar el ejemplo
        data = SurveyAnalysisService.get_analysis_data(survey, qs, include_charts=True)
        pptx_file = PPTXReportGenerator.generate_report(
            survey=survey,
            analysis_data=data['analysis_data'],
            nps_data=data['nps_data'],
            responses_queryset=qs
        )
        
        response = HttpResponse(pptx_file.getvalue(), content_type='application/vnd.openxmlformats-officedocument.presentationml.presentation')
        response['Content-Disposition'] = f'attachment; filename="Reporte_{survey.public_id}.pptx"'
        return response

    except Exception as e:
        logger.error(f"Error generating PowerPoint: {e}", exc_info=True)
        return HttpResponse(f"Error: {str(e)}", status=500)


@login_required
def report_pdf_view(request):
    """Genera y descarga el reporte PDF."""
    try:
        public_id = request.GET.get("public_id")
        if not public_id: return HttpResponse("ID requerido", status=400)

        survey = get_object_or_404(Survey.objects.prefetch_related("questions__options"), public_id=public_id)
        PermissionHelper.verify_survey_access(survey, request.user)

        qs = SurveyResponse.objects.filter(survey=survey)
        # Aplicar filtros (simplificado)
        
        data_pack = SurveyAnalysisService.get_analysis_data(survey, qs, include_charts=True)
        
        pdf_file = PDFReportGenerator.generate_report(
            survey=survey,
            analysis_data=data_pack.get("analysis_data", []),
            nps_data=data_pack.get("nps_data"),
            total_responses=qs.count(),
            kpi_satisfaction_avg=data_pack.get("kpi_prom_satisfaccion"),
            request=request,
            is_pdf=True
        )

        response = HttpResponse(pdf_file, content_type="application/pdf")
        filename = f"Reporte_{survey.public_id}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        logger.error(f"[PDF][ERROR] error={e}", exc_info=True)
        return HttpResponse(f"Error generando PDF: {e}", status=500)


@login_required
def settings_view(request):
    return render(request, 'core/dashboard/settings.html', {'page_name': 'settings', 'user': request.user})