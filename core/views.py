# core/views.py
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, Http404
from django.utils import timezone
from django.db.models.functions import TruncDate
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.template.loader import render_to_string
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Count, Avg, Min, Max
from django_ratelimit.decorators import ratelimit
from datetime import datetime, timedelta
import json
import logging

from surveys.models import Survey, SurveyResponse, QuestionResponse
from core.services.survey_analysis import SurveyAnalysisService
from core.reports.pdf_generator import PDFReportGenerator
from core.reports.pptx_generator import PPTXReportGenerator
from core.validators import DateFilterValidator, SurveyValidator
from core.utils.helpers import DateFilterHelper, ResponseDataBuilder, PermissionHelper
from core.utils.logging_utils import StructuredLogger, log_performance, log_security_event

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
        
        # Surveys requiring attention
        seven_days_ago = timezone.now() - timedelta(days=7)
        
        alerts = []
        
        # Low performance active surveys
        for s in user_surveys.filter(status='active').annotate(response_count=Count('responses')):
            if s.sample_goal > 0:
                progress = (s.response_count / s.sample_goal) * 100
                if progress < 30 and s.created_at < seven_days_ago:
                    alerts.append({
                        'id': s.id,
                        'public_id': s.public_id,
                        'titulo': s.title,
                        'title': s.title,
                        'estado': s.status,
                        'status': s.status,
                        'tipo': 'bajo_rendimiento',
                        'icon': 'bi-exclamation-triangle-fill',
                        'color': 'warning',
                        'mensaje': f'Solo {s.response_count} de {s.sample_goal} respuestas ({int(progress)}%)',
                        'respuestas': s.response_count,
                        'fecha': s.updated_at
                    })
        
        # Old drafts
        for s in user_surveys.filter(status='draft', created_at__lt=seven_days_ago)[:3]:
            days = (timezone.now() - s.created_at).days
            alerts.append({
                'id': s.id,
                'public_id': s.public_id,
                'titulo': s.title,
                'title': s.title,
                'estado': s.status,
                'status': s.status,
                'tipo': 'borrador_antiguo',
                'icon': 'bi-clock-history',
                'color': 'info',
                'mensaje': f'En borrador por {days} días',
                'respuestas': 0,
                'fecha': s.updated_at
            })
        
        # Inactive surveys (no responses in 3 days)
        three_days_ago = timezone.now() - timedelta(days=3)
        for s in user_surveys.filter(status='active'):
            last_response = SurveyResponse.objects.filter(survey=s).order_by('-created_at').first()
            if last_response and last_response.created_at < three_days_ago:
                days_no_resp = (timezone.now() - last_response.created_at).days
                if s.id not in [a['id'] for a in alerts]:  # Avoid duplicates
                    alerts.append({
                        'id': s.id,
                        'public_id': s.public_id,
                        'titulo': s.title,
                        'title': s.title,
                        'estado': s.status,
                        'status': s.status,
                        'tipo': 'sin_actividad',
                        'icon': 'bi-hourglass-split',
                        'color': 'secondary',
                        'mensaje': f'Sin respuestas por {days_no_resp} días',
                        'respuestas': SurveyResponse.objects.filter(survey=s).count(),
                        'fecha': last_response.created_at
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
            # --- KEY VARIABLES FOR EMPTY STATE ---
            'total_encuestas_count': total_surveys,
            'total_respuestas_count': total_responses,
        }
        cache.set(cache_key, context, 300)

    return render(request, 'core/dashboard.html', context)

@login_required
def dashboard_results_view(request):
    """
    GLOBAL Results Dashboard View.
    """
    user = request.user
    

    # Soporte para rango personalizado
    start = request.GET.get('start')
    end = request.GET.get('end')
    period = request.GET.get('periodo', '30')
    days = None
    custom_range = False
    if start and end:
        try:
            start_date = datetime.strptime(start, '%Y-%m-%d')
            end_date = datetime.strptime(end, '%Y-%m-%d')
            # Ajustar a zona horaria local
            start_date = timezone.make_aware(start_date)
            end_date = timezone.make_aware(end_date)
            custom_range = True
        except Exception:
            start_date = end_date = None
    if custom_range and start_date and end_date:
        user_surveys = Survey.objects.filter(author=user).select_related('author')
        responses_qs = SurveyResponse.objects.filter(survey__author=user).select_related('survey')
        responses_qs = responses_qs.filter(created_at__date__gte=start_date.date(), created_at__date__lte=end_date.date())
    else:
        # Determine days based on period
        if period == 'all':
            days = None
        else:
            try:
                days = int(period)
            except ValueError:
                days = 30  # Default
        user_surveys = Survey.objects.filter(author=user).select_related('author')
        responses_qs = SurveyResponse.objects.filter(survey__author=user).select_related('survey')
        # Apply period filter
        if days is not None:
            start_date = timezone.now() - timedelta(days=days)
            responses_qs = responses_qs.filter(created_at__gte=start_date)

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
    
    # Top 5 Surveys
    top_surveys = user_surveys.annotate(
        response_count=Count('responses')
    ).order_by('-response_count')[:5]
    
    # Status Distribution
    status_counts = user_surveys.values('status').annotate(
        count=Count('id')
    ).order_by('-count')
    
    status_names = {
        'draft': 'Borrador',
        'active': 'Activas',
        'closed': 'Cerradas',
        'archived': 'Archivadas'
    }
    
    category_labels = [status_names.get(e['status'], e['status']) for e in status_counts]
    category_data = [e['count'] for e in status_counts]
    
    # Top 10 Questions
    from surveys.models import Question
    top_questions = Question.objects.filter(
        survey__author=user,
        type='scale'
    ).annotate(
        avg_score=Avg('questionresponse__numeric_value'),
        num_responses=Count('questionresponse')
    ).filter(
        num_responses__gte=5
    ).order_by('-avg_score')[:10]
    
    # Weekly Trend
    weeks_data = []
    today = timezone.now().date()
    for i in range(3, -1, -1):
        week_start = today - timedelta(days=(i+1)*7)
        week_end = today - timedelta(days=i*7)
        week_count = responses_qs.filter(
            created_at__date__gte=week_start,
            created_at__date__lt=week_end
        ).count()
        weeks_data.append(week_count)
    
    if len(weeks_data) >= 2 and weeks_data[-2] > 0:
        weekly_change = round(((weeks_data[-1] - weeks_data[-2]) / weeks_data[-2]) * 100, 1)
    else:
        weekly_change = 0

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
    return render(request, 'core/results_dashboard.html', context)


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

    # Top 5 Surveys
    top_surveys = user_surveys.annotate(
        response_count=Count('responses')
    ).order_by('-response_count')[:5]
    
    # Recent Surveys
    recent_surveys = user_surveys.order_by('-created_at')[:5]
    
    # Top 10 Questions
    from surveys.models import Question
    top_questions = Question.objects.filter(
        survey__author=user,
        type='scale'
    ).annotate(
        avg_score=Avg('questionresponse__numeric_value'),
        num_responses=Count('questionresponse')
    ).filter(
        num_responses__gte=5
    ).order_by('-avg_score')[:10]
    
    # Category Distribution
    categories = user_surveys.values('category').annotate(
        count=Count('id')
    ).order_by('-count')[:5]
    
    category_distribution = [(c['category'] or 'Sin categoría', c['count']) for c in categories]
    
    # Weekly Trend
    weeks_data = []
    today = timezone.now().date()
    for i in range(3, -1, -1):
        week_start = today - timedelta(days=(i+1)*7)
        week_end = today - timedelta(days=i*7)
        week_count = responses_qs.filter(
            created_at__date__gte=week_start,
            created_at__date__lt=week_end
        ).count()
        weeks_data.append(week_count)
    
    if len(weeks_data) >= 2 and weeks_data[-2] > 0:
        weekly_change = round(((weeks_data[-1] - weeks_data[-2]) / weeks_data[-2]) * 100, 1)
    else:
        weekly_change = 0

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
        'top_surveys': top_surveys,
        'recent_surveys': recent_surveys,
        'top_preguntas': top_questions,
        'categoria_distribution': category_distribution,
        'fecha_generacion': datetime.now().strftime('%d/%m/%Y %H:%M'),
    }

    html_string = render_to_string('core/_global_results_pdf.html', context)
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
    context = {
        'page_name': 'reports',
        'surveys': surveys,
    }
    return render(request, 'core/reports_page.html', context)


@login_required
def report_preview_ajax(request, public_id):
    """AJAX View for report preview."""
    try:
        identifier_for_log = public_id
        # Validate boolean params
        show_kpis = SurveyValidator.validate_boolean_param(
            request.GET.get('include_kpis', 'true'), 'include_kpis'
        )
        show_charts = SurveyValidator.validate_boolean_param(
            request.GET.get('include_charts', 'true'), 'include_charts'
        )
        show_table = SurveyValidator.validate_boolean_param(
            request.GET.get('include_table', 'true'), 'include_table'
        )
        
        try:
            survey = get_object_or_404(Survey.objects.prefetch_related('questions__options'), public_id=public_id)
            identifier_for_log = survey.public_id or public_id
        except Http404:
            logger.warning(
                "Intento AJAX de preview de reporte de encuesta inexistente: ID %s desde IP %s por usuario %s",
                public_id,
                request.META.get('REMOTE_ADDR'),
                request.user.username,
            )
            return HttpResponse(json.dumps({'error': 'Encuesta no encontrada'}), content_type='application/json', status=404)
        
        # Permission Check
        PermissionHelper.verify_survey_access(survey, request.user)
        
        qs = SurveyResponse.objects.filter(survey=survey).select_related('survey')

        # Validate and parse dates
        start = request.GET.get('start_date')
        end = request.GET.get('end_date')
        window = request.GET.get('window_days')
        
        if start:
            DateFilterValidator.validate_date_string(start, 'start_date')
        if end:
            DateFilterValidator.validate_date_string(end, 'end_date')
        if window:
            DateFilterValidator.validate_window_days(window)

        # Apply Filters
        qs, start = apply_date_filters(qs, start, end, window)

        # Generate Cache Key
        cache_key = f"survey_analysis_{survey.id}_{start or 'all'}_{end or 'all'}_{window or 'all'}"
        
        # Get Analysis Data
        data = SurveyAnalysisService.get_analysis_data(
            survey, qs, include_charts=True, cache_key=cache_key
        )
        
        json_data = json.dumps(data['analysis_data'], ensure_ascii=False, cls=DjangoJSONEncoder)

        return HttpResponse(
            render_to_string(
                'core/_report_preview_content.html',
                {
                    'survey': survey,
                    'analysis_data': data['analysis_data'],
                    'analysis_data_json': json_data,
                    'nps_score': data['nps_data']['score'],
                    'total_respuestas': qs.count(),
                    'kpi_prom_satisfaccion': data['kpi_prom_satisfaccion'],
                    'include_kpis': show_kpis,
                    'include_charts': show_charts,
                    'include_table': show_table,
                }
            )
        )
    except ValidationError as e:
        logger.error(f"[REPORT][ERROR][VALIDATION] {e}")
        return HttpResponse(str(e), status=400)
    except Exception as e:
        logger.error(f"[REPORT][ERROR][UNEXPECTED] encuesta={identifier_for_log} error={e}", exc_info=True)
        return HttpResponse("Error al generar la vista previa del reporte", status=500)


@login_required
@ratelimit(key='user', rate='10/h', method=['GET', 'POST'], block=True)
def report_pdf_view(request):
    """View to generate and download PDF report."""
    identifier_for_log = None
    try:
        raw_identifier = request.POST.get('survey_id') or request.GET.get('survey_id')
        identifier = SurveyValidator.validate_survey_id(raw_identifier)
        lookup = {'public_id': identifier} if isinstance(identifier, str) else {'pk': identifier}
        identifier_for_log = identifier

        # Load survey with author for template
        survey = get_object_or_404(
            Survey.objects.prefetch_related('questions__options').select_related('author'), 
            **lookup
        )
        identifier_for_log = survey.public_id or survey.id
        
        # Verify permissions
        PermissionHelper.verify_survey_access(survey, request.user)

        start = request.POST.get('start_date') or request.GET.get('start_date')
        end = request.POST.get('end_date') or request.GET.get('end_date')
        window = request.POST.get('window_days')
        include_table = request.POST.get('include_table') == 'on'

        qs = SurveyResponse.objects.filter(survey=survey).select_related('survey')
        
        # Apply date filters
        qs, start = apply_date_filters(qs, start, end, window)

        # Cache Key
        cache_key = f"survey_analysis_{survey.id}_{start or 'all'}_{end or 'all'}_{window or 'all'}"

        # Get Analysis Data
        data_pack = SurveyAnalysisService.get_analysis_data(
            survey, qs, include_charts=True, cache_key=cache_key
        )

        # Generate PDF
        # FIXED: Using correct English parameter names for the generator
        pdf_file = PDFReportGenerator.generate_report(
            survey=survey,
            analysis_data=data_pack['analysis_data'],
            nps_data=data_pack['nps_data'],
            start_date=start,
            end_date=end,
            total_responses=qs.count(),          # Corrected param name
            include_table=include_table,
            kpi_satisfaction_avg=data_pack['kpi_prom_satisfaccion'], # Corrected param name
            request=request
        )

        response = HttpResponse(pdf_file, content_type='application/pdf')
        filename = PDFReportGenerator.get_filename(survey)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except ValidationError as e:
        logger.error(f"[PDF][ERROR][VALIDATION] {e}")
        return HttpResponse(str(e), status=400)
    except ValueError as e:
        logger.error(f"[PDF][ERROR][VALIDATION] {e}")
        return HttpResponse(str(e), status=500)
    except Exception as e:
        logger.error(f"[PDF][ERROR][UNEXPECTED] encuesta={identifier_for_log} error={e}", exc_info=True)
        return HttpResponse("Error generating PDF", status=500)


@login_required
def report_powerpoint_view(request):
    """View to generate and download PowerPoint report."""
    if request.method != 'POST':
        return HttpResponse("Method not allowed.", status=405)

    identifier_for_log = None
    try:
        raw_identifier = request.POST.get('survey_id')
        identifier = SurveyValidator.validate_survey_id(raw_identifier)
        lookup = {'public_id': identifier} if isinstance(identifier, str) else {'pk': identifier}
        identifier_for_log = identifier

        # Load survey
        survey = get_object_or_404(
            Survey.objects.prefetch_related('questions__options').select_related('author'), 
            **lookup
        )
        identifier_for_log = survey.public_id or survey.id
        
        # Verify permissions
        PermissionHelper.verify_survey_access(survey, request.user)

        qs = SurveyResponse.objects.filter(survey=survey).select_related('survey')

        start = request.POST.get('start_date')
        end = request.POST.get('end_date')
        window = request.POST.get('window_days')
        
        # Date Range Label
        date_range_label = "Todo el histórico"
        if start:
            start_date = datetime.strptime(start, '%Y-%m-%d').date()
            date_range_label = f"Desde {start_date.strftime('%d/%m/%Y')}"
        elif window and window.isdigit():
            days = int(window)
            date_range_label = f"Últimos {days} días"
        
        if end:
            end_date = datetime.strptime(end, '%Y-%m-%d').date()
            date_range_label += f" hasta {end_date.strftime('%d/%m/%Y')}"

        # Apply Filters
        qs, start = apply_date_filters(qs, start, end, window)

        # Cache Key
        cache_key = f"survey_analysis_{survey.id}_{start or 'all'}_{end or 'all'}_{window or 'all'}"

        # Get Analysis
        data = SurveyAnalysisService.get_analysis_data(
            survey, qs, include_charts=True, cache_key=cache_key
        )

        # Generate PPTX
        # FIXED: Using correct English parameter names for the generator
        pptx_file = PPTXReportGenerator.generate_report(
            survey=survey,                     # Corrected param name (was 'encuesta')
            analysis_data=data['analysis_data'],
            nps_data=data['nps_data'],
            heatmap_image=data['heatmap_image'],
            date_range_label=date_range_label,
            responses_queryset=qs              # Corrected param name (was 'respuestas_queryset')
        )

        response = HttpResponse(
            pptx_file.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.presentationml.presentation'
        )
        filename = f"Reporte_{survey.public_id or survey.id}.pptx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
        
    except ValidationError as e:
        logger.error(f"[PPTX][ERROR][VALIDATION] {e}")
        return HttpResponse(str(e), status=400)
    except Exception as e:
        logger.exception(f"Error generating PowerPoint: encuesta={identifier_for_log} error={e}")
        return HttpResponse(f"Error generating PowerPoint: {str(e)}", status=500)


@login_required
def settings_view(request):
    return render(
        request,
        'core/settings.html',
        {'page_name': 'settings', 'user': request.user}
    )