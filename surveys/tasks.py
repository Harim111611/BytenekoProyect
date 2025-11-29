# ============================================================
# BULK DELETE SURVEYS TASK (HEAVY/ASYNC)
# ============================================================

from django.db import connection, transaction
from surveys.models import Survey

# Ensure Celery helpers and logger are available before defining tasks
from celery import shared_task
from django.core.cache import cache
from django.utils import timezone
from django.db.models import Count, Avg, F
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


def perform_delete_surveys(survey_ids, user_id):
    """
    Helper that performs the actual deletion synchronously.
    This can be called from the Celery task or from a background thread
    when Celery is configured to run in eager/synchronous mode.
    Returns dict similar to the Celery task.
    """
    try:
        owned_ids = list(Survey.objects.filter(id__in=survey_ids, author_id=user_id).values_list('id', flat=True))
        if not owned_ids:
            logger.warning(f"[DELETE][HELPER] No owned surveys to delete for user_id={user_id}")
            return {'success': False, 'deleted': 0, 'error': 'No owned surveys'}
        with transaction.atomic():
            with connection.cursor() as cursor:
                logger.info(f"[DELETE][HELPER] Eliminando encuestas {owned_ids} para user_id={user_id}")
                # reuse existing fast delete helper from views
                from surveys.views.crud_views import _fast_delete_surveys
                _fast_delete_surveys(cursor, owned_ids)
        for sid in owned_ids:
            cache.delete(f"survey_stats_{sid}")
        cache.delete(f"survey_count_user_{user_id}")
        cache.delete(f"dashboard_data_user_{user_id}")
        logger.info(f"[DELETE][HELPER] Eliminación completada para {len(owned_ids)} encuestas")
        return {'success': True, 'deleted': len(owned_ids)}
    except Exception as exc:
        logger.error(f"[DELETE][HELPER] Error: {exc}", exc_info=True)
        return {'success': False, 'deleted': 0, 'error': str(exc)}


@shared_task(
    bind=True,
    name='surveys.tasks.delete_surveys_task',
    queue='default',
    max_retries=2,
    default_retry_delay=60,
)
def delete_surveys_task(self, survey_ids, user_id):
    """
    Elimina encuestas y sus datos relacionados de forma optimizada y asíncrona.
    Valida que las encuestas pertenezcan al usuario antes de borrar.
    Args:
        survey_ids (list): IDs de encuestas a eliminar
        user_id (int): ID del usuario solicitante
    Returns:
        dict: {'success': bool, 'deleted': int, 'error': str}
    """
    from surveys.views.crud_views import _fast_delete_surveys
    try:
        # Delegate to helper that performs the actual deletion logic
        result = perform_delete_surveys(survey_ids, user_id)
        if not result.get('success'):
            # If helper returned error, raise to trigger retry
            raise Exception(result.get('error') or 'Unknown error in delete helper')
        logger.info(f"[CELERY][DELETE] Eliminación asíncrona completada para {result.get('deleted', 0)} encuestas")
        return result
    except Exception as exc:
        logger.error(f"[CELERY][DELETE] Error: {exc}", exc_info=True)
        raise self.retry(exc=exc)
# ============================================================
# REPORT GENERATION TASKS
# ============================================================

@shared_task(
    bind=True,
    name='surveys.tasks.generate_pdf_report',
    queue='reports',
    max_retries=3,
    default_retry_delay=60,
)
def generate_pdf_report(self, survey_id, user_id=None):
    """
    Generate PDF report for a survey asynchronously.
    
    Args:
        survey_id: Survey ID
        user_id: User requesting the report (for notifications)
    
    Returns:
        dict: {'success': bool, 'file_path': str, 'error': str}
    """
    try:
        from surveys.models import Survey
        from core.reports.pdf_generator import PDFReportGenerator
        
        logger.info(f"Starting PDF generation for survey {survey_id}")
        
        survey = Survey.objects.select_related('creador').get(id=survey_id)
        generator = PDFReportGenerator(survey)
        file_path = generator.generate()
        
        logger.info(f"PDF generated successfully: {file_path}")
        
        # Store result in cache for 1 hour
        cache_key = f'pdf_report_{survey_id}_{user_id or "anon"}'
        cache.set(cache_key, {'status': 'completed', 'file_path': file_path}, 3600)
        
        return {'success': True, 'file_path': str(file_path)}
        
    except Encuesta.DoesNotExist:
        logger.error(f"Survey {survey_id} not found")
        return {'success': False, 'error': 'Survey not found'}
        
    except Exception as exc:
        logger.error(f"Error generating PDF for survey {survey_id}: {exc}")
        # Retry task
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name='surveys.tasks.generate_pptx_report',
    queue='reports',
    max_retries=3,
    default_retry_delay=60,
)
def generate_pptx_report(self, survey_id, user_id=None):
    """
    Generate PowerPoint report for a survey asynchronously.
    
    Args:
        survey_id: Survey ID
        user_id: User requesting the report
    
    Returns:
        dict: {'success': bool, 'file_path': str, 'error': str}
    """
    try:
        from surveys.models import Survey
        from core.reports.pptx_generator import PPTXReportGenerator
        
        logger.info(f"Starting PPTX generation for survey {survey_id}")
        
        survey = Survey.objects.select_related('creador').get(id=survey_id)
        generator = PPTXReportGenerator(survey)
        file_path = generator.generate()
        
        logger.info(f"PPTX generated successfully: {file_path}")
        
        # Store result in cache
        cache_key = f'pptx_report_{survey_id}_{user_id or "anon"}'
        cache.set(cache_key, {'status': 'completed', 'file_path': file_path}, 3600)
        
        return {'success': True, 'file_path': str(file_path)}
        
    except Encuesta.DoesNotExist:
        logger.error(f"Survey {survey_id} not found")
        return {'success': False, 'error': 'Survey not found'}
        
    except Exception as exc:
        logger.error(f"Error generating PPTX for survey {survey_id}: {exc}")
        raise self.retry(exc=exc)


# ============================================================
# CHART GENERATION TASKS
# ============================================================

@shared_task(
    bind=True,
    name='surveys.tasks.generate_chart_image',
    queue='charts',
    max_retries=2,
)
def generate_chart_image(self, survey_id, question_id, chart_type='bar'):
    """
    Generate chart image for a specific question.
    
    Args:
        survey_id: Survey ID
        question_id: Question ID
        chart_type: Type of chart ('bar', 'pie', 'line')
    
    Returns:
        dict: {'success': bool, 'image_path': str}
    """
    try:
        from surveys.models import Survey, Question
        from core.utils.charts import generate_question_chart
        
        logger.info(f"Generating {chart_type} chart for question {question_id}")
        
        question = Question.objects.select_related('survey').get(id=question_id)
        image_path = generate_question_chart(question, chart_type)
        
        logger.info(f"Chart generated: {image_path}")
        
        return {'success': True, 'image_path': str(image_path)}
        
    except Pregunta.DoesNotExist:
        logger.error(f"Question {question_id} not found")
        return {'success': False, 'error': 'Question not found'}
        
    except Exception as exc:
        logger.error(f"Error generating chart: {exc}")
        raise self.retry(exc=exc)


# ============================================================
# DATA IMPORT TASKS
# ============================================================

@shared_task(
    bind=True,
    name='surveys.tasks.import_csv_responses',
    queue='imports',
    max_retries=1,
)
def import_csv_responses(self, survey_id, csv_file_path, user_id):
    """
    Import CSV responses asynchronously.
    
    NOTE: La lógica de importación CSV está en surveys/views.py
    Esta tarea puede ser implementada cuando se extraiga a un servicio dedicado.
    
    Args:
        survey_id: Survey ID
        csv_file_path: Path to CSV file
        user_id: User who initiated the import
    
    Returns:
        dict: Import results
    """
    logger.warning("CSV import task not yet fully implemented. See surveys/views.py for current implementation.")
    return {'success': False, 'error': 'Not implemented - use view-based import'}


# ============================================================
# MAINTENANCE TASKS
# ============================================================

@shared_task(name='surveys.tasks.cleanup_old_responses')
def cleanup_old_responses():
    """
    Clean up responses older than 2 years (configurable).
    Runs daily at 3 AM via Celery Beat.
    """
    try:
        from surveys.models import SurveyResponse
        
        cutoff_date = timezone.now() - timedelta(days=730)  # 2 years
        
        old_responses = SurveyResponse.objects.filter(
            created_at__lt=cutoff_date,
            survey__status='archived'
        )
        
        count = old_responses.count()
        old_responses.delete()
        
        logger.info(f"Cleaned up {count} old responses")
        return {'deleted': count}
        
    except Exception as exc:
        logger.error(f"Cleanup error: {exc}")
        return {'error': str(exc)}


@shared_task(name='surveys.tasks.generate_monthly_reports')
def generate_monthly_reports():
    """
    Generate monthly summary reports for all active surveys.
    Runs on the first day of each month at 4 AM.
    """
    try:
        from surveys.models import Survey
        
        active_surveys = Survey.objects.filter(status='active').values_list('id', flat=True)
        
        results = []
        for survey_id in active_surveys:
            result = generate_pdf_report.delay(survey_id)
            results.append({'survey_id': survey_id, 'task_id': result.id})
        
        logger.info(f"Generated {len(results)} monthly reports")
        return {'reports': results}
        
    except Exception as exc:
        logger.error(f"Monthly reports error: {exc}")
        return {'error': str(exc)}


@shared_task(name='surveys.tasks.cleanup_cache')
def cleanup_cache():
    """
    Clean up expired cache entries.
    Runs daily at 2:30 AM.
    """
    try:
        # Django-redis handles expiration automatically
        # This task can be used for custom cleanup logic
        logger.info("Cache cleanup completed")
        return {'success': True}
        
    except Exception as exc:
        logger.error(f"Cache cleanup error: {exc}")
        return {'error': str(exc)}


# ============================================================
# ANALYSIS TASKS
# ============================================================

@shared_task(
    bind=True,
    name='surveys.tasks.analyze_survey_data',
    queue='charts',
)
def analyze_survey_data(self, survey_id):
    """
    Perform heavy statistical analysis on survey data.
    
    Args:
        survey_id: Survey ID
    
    Returns:
        dict: Analysis results
    """
    try:
        from surveys.models import Survey, SurveyResponse
        from core.services.survey_analysis import SurveyAnalysisService
        
        logger.info(f"Starting analysis for survey {survey_id}")
        
        survey = Survey.objects.prefetch_related('preguntas', 'respuestas').get(id=survey_id)
        qs = SurveyResponse.objects.filter(survey=survey)
        
        # Generar clave de caché
        cache_key = f"survey_analysis_{survey_id}"
        
        # Obtener datos de análisis
        data = SurveyAnalysisService.get_analysis_data(
            survey, qs, include_charts=True, cache_key=cache_key
        )
        
        # Cache analysis results for 30 minutes
        cache.set(cache_key, data, 1800)
        
        logger.info(f"Analysis completed for survey {survey_id}")
        return data
        
    except Encuesta.DoesNotExist:
        logger.error(f"Survey {survey_id} not found")
        return {'error': 'Survey not found'}
        
    except Exception as exc:
        logger.error(f"Analysis error: {exc}")
        raise self.retry(exc=exc)


@shared_task(name='surveys.tasks.update_survey_statistics')
def update_survey_statistics(survey_id):
    """
    Update cached statistics for a survey.
    Called after new responses are submitted.
    """
    try:
        from surveys.models import Survey
        
        survey = Survey.objects.prefetch_related('respuestas').get(id=survey_id)
        
        stats = {
            'total_responses': survey.responses.count(),
            'completion_rate': survey.responses.filter(completada=True).count() / survey.responses.count() if survey.responses.exists() else 0,
            'last_response': survey.responses.order_by('-created_at').first().created_at if survey.responses.exists() else None,
        }
        
        cache_key = f'survey_stats_{survey_id}'
        cache.set(cache_key, stats, 600)  # 10 minutes
        
        return stats
        
    except Exception as exc:
        logger.error(f"Statistics update error: {exc}")
        return {'error': str(exc)}
