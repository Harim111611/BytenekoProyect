# ============================================================
# BULK DELETE SURVEYS TASK (HEAVY/ASYNC)
# ============================================================

from django.db import connection, transaction
import time
import logging
from django.db import transaction
from surveys.models import Survey
from django.core.cache import cache

logger = logging.getLogger('surveys')

def perform_delete_surveys(survey_ids, user_or_id):
    """
    BORRADO SÍNCRONO, SIMPLE Y CONFIABLE

    - Acepta lista de IDs de encuestas.
    - Acepta tanto un objeto User como un ID de usuario.
    - Usa el ORM de Django (.delete()) para garantizar borrado real en BD.
    - Devuelve dict: {'success': bool, 'deleted': int, 'error': str | None}
    """

    # 1) Normalizar user_id
    if hasattr(user_or_id, "pk"):
        user_id = user_or_id.pk
    else:
        try:
            user_id = int(user_or_id)
        except (TypeError, ValueError):
            logger.error("[DELETE][HELPER] user_or_id inválido: %r", user_or_id)
            return {'success': False, 'deleted': 0, 'error': 'Invalid user id'}

    start = time.monotonic()
    logger.info("[DELETE][HELPER] START survey_ids=%s user_id=%s", survey_ids, user_id)

    try:
        # 2) Encapsular en transacción
        with transaction.atomic():
            # Filtrar solo encuestas del usuario
            qs = Survey.objects.filter(id__in=survey_ids, author_id=user_id)
            owned_ids = list(qs.values_list("id", flat=True))

            if not owned_ids:
                elapsed = int((time.monotonic() - start) * 1000)
                logger.warning(
                    "[DELETE][HELPER] No owned surveys to delete for user_id=%s "
                    "(survey_ids=%s, elapsed_ms=%d)",
                    user_id,
                    survey_ids,
                    elapsed,
                )
                return {'success': False, 'deleted': 0, 'error': 'No owned surveys'}

            # 3) Borrado real en BD (con cascada)
            deleted_count, _ = qs.delete()

        # 4) Limpiar caches
        try:
            cache.delete(f"dashboard_data_user_{user_id}")
            cache.delete(f"survey_count_user_{user_id}")
            for sid in owned_ids:
                cache.delete(f"survey_stats_{sid}")
        except Exception:
            logger.exception("[DELETE][HELPER] Error invalidando caché post-delete")

        total_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "[DELETE][HELPER] END surveys=%s user_id=%s deleted=%d total_ms=%d",
            owned_ids,
            user_id,
            deleted_count,
            total_ms,
        )
        return {'success': True, 'deleted': deleted_count, 'error': None}

    except Exception as exc:
        total_ms = int((time.monotonic() - start) * 1000)
        logger.error(
            "[DELETE][HELPER] ERROR user_id=%s survey_ids=%s elapsed_ms=%d error=%s",
            user_id,
            survey_ids,
            total_ms,
            str(exc),
            exc_info=True,
        )
        return {'success': False, 'deleted': 0, 'error': str(exc)}
    except Exception as exc:
        total_elapsed = int((time.monotonic() - start) * 1000)
        logger.error(
            "[DELETE][HELPER] ERROR user_id=%s survey_ids=%s elapsed_ms=%d error=%s",
            user_id_val,
            survey_ids,
            total_elapsed,
            str(exc),
            exc_info=True,
        )
        return {
            'success': False,
            'deleted': 0,
            'error': str(exc),
        }


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
    default_retry_delay=60,
    import time
    import logging
    logger = logging.getLogger('surveys')

@shared_task(
        """
        Helper que realiza la eliminación sincrónica.
        Se usa tanto desde la tarea Celery como desde el hilo en modo eager.
        Ahora incluye métricas de tiempo para entender el costo real del delete.
        """
        start = time.monotonic()
        logger.info(f"[DELETE][HELPER] START survey_ids={survey_ids} user_id={user_id}")
        try:
            owned_ids = list(
                Survey.objects
                .filter(id__in=survey_ids, author_id=user_id)
                .values_list('id', flat=True)
            )
            if not owned_ids:
                elapsed = time.monotonic() - start
                logger.warning(
                    f"[DELETE][HELPER] No owned surveys to delete for user_id={user_id} "
                    f"(elapsed={int(elapsed * 1000)}ms)"
                )
                return {'success': False, 'deleted': 0, 'error': 'No owned surveys'}

            sql_start = time.monotonic()
            with transaction.atomic():
                with connection.cursor() as cursor:
                    # Aquí se llama al eliminador rápido
                    from surveys.views.crud_views import _fast_delete_surveys
                    _fast_delete_surveys(cursor, owned_ids)
            sql_elapsed = time.monotonic() - sql_start

            # Invalidar caches relacionados
            cache_start = time.monotonic()
            for sid in owned_ids:
                cache.delete(f"survey_stats_{sid}")
            cache.delete(f"survey_count_user_{user_id}")
            cache.delete(f"dashboard_data_user_{user_id}")
            cache_elapsed = time.monotonic() - cache_start

            total_elapsed = time.monotonic() - start
            logger.info(
                "[DELETE][HELPER] END surveys=%s user_id=%s "
                "total_ms=%d sql_ms=%d cache_ms=%d",
                owned_ids,
                user_id,
                int(total_elapsed * 1000),
                int(sql_elapsed * 1000),
                int(cache_elapsed * 1000),
            )
            return {'success': True, 'deleted': len(owned_ids)}

        except Exception as exc:
            total_elapsed = time.monotonic() - start
            logger.error(
                "[DELETE][HELPER] ERROR user_id=%s survey_ids=%s elapsed_ms=%d error=%s",
                user_id,
                survey_ids,
                int(total_elapsed * 1000),
                str(exc),
                exc_info=True,
            )
            return {'success': False, 'deleted': 0, 'error': str(exc)}
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
