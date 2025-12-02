import logging
import os
import time
from datetime import timedelta

import pandas as pd
from surveys.models import AnswerOption
from celery import shared_task
from django.core.cache import cache
from django.db import connection, transaction
from django.utils import timezone

from surveys.models import Survey, Question, SurveyResponse, ImportJob
from surveys.utils.bulk_import import bulk_import_responses_postgres

logger = logging.getLogger("surveys")


# ============================================================
# BULK DELETE SURVEYS TASK (HEAVY/ASYNC)
# ============================================================


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
            return {"success": False, "deleted": 0, "error": "Invalid user id"}

    start = time.monotonic()
    logger.info(f"[DELETE][START] user_id={user_id} survey_ids={survey_ids}")

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
                return {"success": False, "deleted": 0, "error": "No owned surveys"}

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
        logger.info(f"[DELETE][END] user_id={user_id} survey_ids={owned_ids} deleted={deleted_count} time_ms={total_ms}")
        return {"success": True, "deleted": deleted_count, "error": None}

    except Exception as exc:
        total_ms = int((time.monotonic() - start) * 1000)
        logger.error(f"[DELETE][ERROR] user_id={user_id} survey_ids={survey_ids} time_ms={total_ms} error={str(exc)}", exc_info=True)
        return {"success": False, "deleted": 0, "error": str(exc)}


@shared_task(
    bind=True,
    name="surveys.tasks.delete_surveys_task",
    queue="default",
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
    try:
        result = perform_delete_surveys(survey_ids, user_id)
        if not result.get("success"):
            # If helper returned error, raise to trigger retry
            raise Exception(result.get("error") or "Unknown error in delete helper")
        logger.info(
            "[CELERY][DELETE] Eliminación asíncrona completada para %d encuestas",
            result.get("deleted", 0),
        )
        return result
    except Exception as exc:
        logger.error("[CELERY][DELETE] Error: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


# ============================================================
# REPORT GENERATION TASKS
# ============================================================


@shared_task(
    bind=True,
    name="surveys.tasks.generate_pptx_report",
    queue="reports",
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
        from core.reports.pptx_generator import PPTXReportGenerator

        logger.info("Starting PPTX generation for survey %s", survey_id)

        # Nota: ajustado a 'author' en vez de 'creador'
        survey = Survey.objects.select_related("author").get(id=survey_id)
        generator = PPTXReportGenerator(survey)
        file_path = generator.generate()

        logger.info("PPTX generated successfully: %s", file_path)

        # Store result in cache
        cache_key = f"pptx_report_{survey_id}_{user_id or 'anon'}"
        cache.set(
            cache_key,
            {"status": "completed", "file_path": str(file_path)},
            3600,
        )

        return {"success": True, "file_path": str(file_path)}

    except Survey.DoesNotExist:
        logger.error("Survey %s not found", survey_id)
        return {"success": False, "error": "Survey not found"}

    except Exception as exc:
        logger.error("Error generating PPTX for survey %s: %s", survey_id, exc)
        raise self.retry(exc=exc)


# ============================================================
# CHART GENERATION TASKS
# ============================================================


@shared_task(
    bind=True,
    name="surveys.tasks.generate_chart_image",
    queue="charts",
    max_retries=2,
)
def generate_chart_image(self, survey_id, question_id, chart_type="bar"):
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
        from core.utils.charts import generate_question_chart

        logger.info(
            "Generating %s chart for question %s (survey %s)",
            chart_type,
            question_id,
            survey_id,
        )

        question = Question.objects.select_related("survey").get(id=question_id)
        image_path = generate_question_chart(question, chart_type)

        logger.info("Chart generated: %s", image_path)

        return {"success": True, "image_path": str(image_path)}

    except Question.DoesNotExist:
        logger.error("Question %s not found", question_id)
        return {"success": False, "error": "Question not found"}

    except Exception as exc:
        logger.error("Error generating chart: %s", exc)
        raise self.retry(exc=exc)


# ============================================================
# DATA IMPORT TASKS (CSV -> SURVEY)
# ============================================================


@shared_task(
    bind=True,
    name="surveys.tasks.process_survey_import",
    queue="imports",
    max_retries=1,
)
def process_survey_import(self, import_job_id):
    """
    Procesa la importación de un archivo CSV en background usando batches/chunks.
    Actualiza el estado y progreso en ImportJob.
    """
    try:
        job = ImportJob.objects.get(id=import_job_id)
        job.status = "processing"
        job.save(update_fields=["status", "updated_at"])

        chunk_size = 1000
        encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
        csv_path = job.csv_file
        user = job.user
        title = (
            os.path.basename(csv_path)
            .replace(".csv", "")
            .replace("_", " ")
            .title()
        )
        survey = None
        questions_map = {}
        total_rows = 0

        # Intentar distintos encodings y crear Survey + Questions a partir del primer chunk
        for encoding in encodings:
            try:
                chunk_iter = pd.read_csv(
                    csv_path,
                    encoding=encoding,
                    chunksize=chunk_size,
                )
                first_chunk = next(chunk_iter)
                df_columns = first_chunk.columns

                with transaction.atomic():
                    survey = Survey.objects.create(
                        title=title[:255],
                        description=f"Importado automáticamente desde {csv_path}",
                        status="active",
                        author=user,
                    )
                    questions = []
                    questions_map_temp = {}
                    for idx, col_name in enumerate(df_columns):
                        sample = first_chunk[col_name].dropna()
                        col_type = "text"
                        if pd.api.types.is_numeric_dtype(sample):
                            if not sample.empty and sample.min() >= 0 and sample.max() <= 10:
                                col_type = "scale"
                            else:
                                col_type = "number"
                        elif sample.astype(str).str.contains(",").any():
                            col_type = "multi"
                        elif sample.nunique() < 20:
                            col_type = "single"
                        q = Question(
                            survey=survey,
                            text=col_name[:500],
                            type=col_type,
                            order=idx,
                        )
                        questions.append(q)
                        questions_map_temp[col_name] = {"question": q, "dtype": col_type}
                    Question.objects.bulk_create(questions)
                    # Asignar instancias reales a questions_map
                    for idx, col_name in enumerate(df_columns):
                        q = Question.objects.filter(survey=survey, order=idx).first()
                        col_type = questions_map_temp[col_name]["dtype"]
                        entry = {"question": q, "dtype": col_type}
                        # Si es single/multi, crear AnswerOption y options
                        if col_type in ("single", "multi"):
                            unique_values = sample.astype(str).unique()
                            options = []
                            for order, val in enumerate(unique_values):
                                val_norm = val.strip()
                                ao, _ = AnswerOption.objects.get_or_create(question=q, text=val_norm, defaults={"order": order})
                                options.append((val_norm, ao))
                            entry["options"] = {k: v for k, v in options}
                        questions_map[col_name] = entry
                break
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logger.error("Error al procesar chunk inicial: %s", e, exc_info=True)
                continue
        else:
            job.status = "failed"
            job.error_message = (
                "No se pudo leer el archivo CSV. Verifique la codificación."
            )
            job.save(update_fields=["status", "error_message", "updated_at"])
            return {"success": False, "error": job.error_message}

        def process_chunk(chunk):
            nonlocal total_rows
            total_rows += len(chunk)
            bulk_import_responses_postgres(survey, chunk, questions_map)
            job.processed_rows = total_rows
            job.save(update_fields=["processed_rows", "updated_at"])

        # Procesar el primer chunk y el resto
        process_chunk(first_chunk)
        for chunk in chunk_iter:
            process_chunk(chunk)

        job.status = "completed"
        job.survey = survey
        job.total_rows = total_rows
        job.save(
            update_fields=[
                "status",
                "survey",
                "total_rows",
                "processed_rows",
                "updated_at",
            ]
        )
        return {"success": True, "survey_id": survey.id, "rows": total_rows}
    except Exception as exc:
        logger.error("Error en importación async: %s", exc, exc_info=True)
        job = ImportJob.objects.filter(id=import_job_id).first()
        if job:
            job.status = "failed"
            job.error_message = str(exc)
            job.save(update_fields=["status", "error_message", "updated_at"])
        return {"success": False, "error": str(exc)}


# ============================================================
# MAINTENANCE TASKS
# ============================================================


@shared_task(name="surveys.tasks.cleanup_old_responses")
def cleanup_old_responses():
    """
    Clean up responses older than 2 years (configurable).
    Runs daily at 3 AM via Celery Beat.
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=730)  # 2 years

        old_responses = SurveyResponse.objects.filter(
            created_at__lt=cutoff_date,
            survey__status="archived",
        )

        count = old_responses.count()
        old_responses.delete()

        logger.info("Cleaned up %d old responses", count)
        return {"deleted": count}

    except Exception as exc:
        logger.error("Cleanup error: %s", exc)
        return {"error": str(exc)}


@shared_task(name="surveys.tasks.generate_monthly_reports")
def generate_monthly_reports():
    """
    Generate monthly summary reports for all active surveys.
    Runs on the first day of each month at 4 AM.
    """
    try:
        active_surveys = Survey.objects.filter(status="active").values_list(
            "id", flat=True
        )

        results = []
        # Nota: se asume que existe una tarea generate_pdf_report en otro módulo.
        # Ajusta este import según tu proyecto real.
        from core.tasks import generate_pdf_report

        for survey_id in active_surveys:
            result = generate_pdf_report.delay(survey_id)
            results.append({"survey_id": survey_id, "task_id": result.id})

        logger.info("Generated %d monthly reports", len(results))
        return {"reports": results}

    except Exception as exc:
        logger.error("Monthly reports error: %s", exc)
        return {"error": str(exc)}


@shared_task(name="surveys.tasks.cleanup_cache")
def cleanup_cache():
    """
    Clean up expired cache entries.
    Runs daily at 2:30 AM.
    """
    try:
        # Django-redis maneja expiración automáticamente.
        # Esta tarea queda para lógica custom si la necesitas.
        logger.info("Cache cleanup completed")
        return {"success": True}

    except Exception as exc:
        logger.error("Cache cleanup error: %s", exc)
        return {"error": str(exc)}


# ============================================================
# ANALYSIS TASKS
# ============================================================


@shared_task(
    bind=True,
    name="surveys.tasks.analyze_survey_data",
    queue="charts",
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
        from core.services.survey_analysis import SurveyAnalysisService

        logger.info("Starting analysis for survey %s", survey_id)

        # Ojo: aquí asumimos related_name en inglés ('questions', 'responses')
        survey = Survey.objects.prefetch_related("questions", "responses").get(
            id=survey_id
        )
        qs = SurveyResponse.objects.filter(survey=survey)

        # Generar clave de caché
        cache_key = f"survey_analysis_{survey_id}"

        # Obtener datos de análisis
        data = SurveyAnalysisService.get_analysis_data(
            survey,
            qs,
            include_charts=True,
            cache_key=cache_key,
        )

        # Cache analysis results for 30 minutes
        cache.set(cache_key, data, 1800)

        logger.info("Analysis completed for survey %s", survey_id)
        return data

    except Survey.DoesNotExist:
        logger.error("Survey %s not found", survey_id)
        return {"error": "Survey not found"}

    except Exception as exc:
        logger.error("Analysis error: %s", exc)
        raise self.retry(exc=exc)


@shared_task(name="surveys.tasks.update_survey_statistics")
def update_survey_statistics(survey_id):
    """
    Update cached statistics for a survey.
    Called after new responses are submitted.
    """
    try:
        survey = Survey.objects.prefetch_related("responses").get(id=survey_id)

        total_responses = survey.responses.count()
        if total_responses:
            # OJO: si el campo ya no se llama 'completada', cámbialo aquí
            completed_count = survey.responses.filter(completada=True).count()
            completion_rate = completed_count / total_responses
            last_response_obj = survey.responses.order_by("-created_at").first()
            last_response_ts = (
                last_response_obj.created_at if last_response_obj else None
            )
        else:
            completion_rate = 0
            last_response_ts = None

        stats = {
            "total_responses": total_responses,
            "completion_rate": completion_rate,
            "last_response": last_response_ts,
        }

        cache_key = f"survey_stats_{survey_id}"
        cache.set(cache_key, stats, 600)  # 10 minutes

        return stats

    except Exception as exc:
        logger.error("Statistics update error: %s", exc)
        return {"error": str(exc)}
