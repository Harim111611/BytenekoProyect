"""
surveys/tasks.py
Tareas asíncronas para reportes, importaciones y mantenimiento.
"""
import logging
import re
from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import transaction, connection
from django.utils import timezone
from django.apps import apps

# Logger
logger = logging.getLogger(__name__)
User = get_user_model()

@shared_task(bind=True)
def process_survey_import(self, job_id: int):
    """
    Procesa un ImportJob en background.
    Actualiza el estado del job en la base de datos para el polling del frontend.
    """
    from surveys.models import ImportJob
    from surveys.utils.bulk_import import bulk_import_responses_postgres

    try:
        job = ImportJob.objects.get(id=job_id)
    except ImportJob.DoesNotExist:
        logger.error(f"[TASK][IMPORT] ImportJob {job_id} no encontrado")
        return {'status': 'FAILURE', 'error': 'job_not_found'}

    try:
        # 1. Marcar como procesando
        job.status = 'processing'
        job.save(update_fields=['status', 'updated_at'])
        
        logger.info(f"[IMPORT] Iniciando Job {job_id} para encuesta {job.survey_id}")

        if not job.survey:
             raise ValueError("La encuesta asociada fue eliminada.")

        # 2. Ejecutar lógica de importación usando el path guardado
        total_rows, imported_rows = bulk_import_responses_postgres(job.csv_file.path, job.survey)

        # 3. Actualizar Job con éxito
        job.status = 'completed'
        job.processed_rows = imported_rows
        job.total_rows = total_rows
        job.save(update_fields=['status', 'processed_rows', 'total_rows', 'updated_at'])

        logger.info(f"[IMPORT] Éxito Job {job_id}. Filas: {total_rows}, Insertadas: {imported_rows}")
        
        return {
            'status': 'SUCCESS',
            'imported_count': imported_rows,
            'total_rows': total_rows,
            'survey_id': job.survey_id,
        }

    except Exception as e:
        logger.exception(f"[TASK][IMPORT] Error crítico en Job {job_id}: {e}")
        
        job.status = 'failed'
        job.error_log = str(e)
        job.error_message = str(e)[:100]
        job.save(update_fields=['status', 'error_log', 'error_message', 'updated_at'])
        
        return {'status': 'FAILURE', 'error': str(e)}

def _normalize_ids(ids) -> list[int]:
    """
    Asegura que ids sea list[int].
    Soporta: int, list/set/tuple, string tipo "(15)" "{15}" "[15,16]".
    """
    if ids is None:
        return []

    if isinstance(ids, int):
        return [ids]

    if isinstance(ids, (list, set, tuple)):
        out: list[int] = []
        for x in ids:
            if x is None:
                continue
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
        return out

    if isinstance(ids, str):
        found = re.findall(r"\d+", ids)
        return [int(x) for x in found]

    # fallback
    try:
        return [int(ids)]
    except (TypeError, ValueError):
        return []


def _existing_tables() -> set[str]:
    return set(connection.introspection.table_names())


def _reportjob_table_name() -> str | None:
    """
    Devuelve el nombre real de la tabla de ReportJob (según Django),
    o None si el modelo no existe/está registrado.
    """
    try:
        Model = apps.get_model("core", "ReportJob")
    except LookupError:
        return None
    return Model._meta.db_table


@shared_task(bind=True)
def bulk_delete_surveys(self, ids):
    """
    Elimina encuestas masivamente usando SQL optimizado (JOIN DELETE).
    """
    try:
        ids_list = _normalize_ids(ids)
        if not ids_list:
            return {"status": "SUCCESS", "deleted": 0}

        tables = _existing_tables()

        with transaction.atomic():
            with connection.cursor() as cursor:
                logger.info(f"[TASK][DELETE] Iniciando borrado optimizado para {len(ids_list)} encuestas: {ids_list}")

                cursor.execute("""
                    DELETE FROM surveys_questionresponse qr
                    USING surveys_surveyresponse sr
                    WHERE qr.survey_response_id = sr.id
                      AND sr.survey_id = ANY(%s::int[])
                """, (ids_list,))

                cursor.execute("""
                    DELETE FROM surveys_surveyresponse
                    WHERE survey_id = ANY(%s::int[])
                """, (ids_list,))

                cursor.execute("""
                    DELETE FROM surveys_answeroption ao
                    USING surveys_question q
                    WHERE ao.question_id = q.id
                      AND q.survey_id = ANY(%s::int[])
                """, (ids_list,))

                cursor.execute("""
                    DELETE FROM surveys_question
                    WHERE survey_id = ANY(%s::int[])
                """, (ids_list,))

                # Jobs asociados (Import)
                if "surveys_importjob" in tables:
                    cursor.execute("""
                        DELETE FROM surveys_importjob
                        WHERE survey_id = ANY(%s::int[])
                    """, (ids_list,))
                else:
                    logger.warning("[TASK][DELETE] Tabla surveys_importjob no existe. Se omite.")

                # Jobs asociados (Report) -> NO hardcodear core_reportjob
                report_table = _reportjob_table_name()
                if report_table and report_table in tables:
                    qt = connection.ops.quote_name(report_table)
                    cursor.execute(f"""
                        DELETE FROM {qt}
                        WHERE survey_id = ANY(%s::int[])
                    """, (ids_list,))
                else:
                    logger.warning(f"[TASK][DELETE] Tabla ReportJob no encontrada (db_table={report_table}). Se omite.")

                # La encuesta en sí
                cursor.execute("""
                    DELETE FROM surveys_survey
                    WHERE id = ANY(%s::int[])
                """, (ids_list,))

                logger.info(f"[TASK][DELETE] Borrado completado para IDs: {ids_list}")

        return {"status": "SUCCESS", "deleted": len(ids_list)}

    except Exception as e:
        logger.error(f"[TASK][DELETE] Error: {e}", exc_info=True)
        return {"status": "FAILURE", "error": str(e)}

@shared_task(bind=True, max_retries=3)
def generate_report_task(self, job_id):
    """
    Tarea para generar reportes PDF/PPTX.
    """
    from core.models_reports import ReportJob
    from surveys.models import SurveyResponse
    from core.reports.pdf_generator import PDFReportGenerator 
    from core.reports.pptx_generator import generate_full_pptx_report
    from core.utils.helpers import DateFilterHelper
    from core.services.survey_analysis import SurveyAnalysisService

    try:
        try:
            job = ReportJob.objects.get(id=job_id)
        except ReportJob.DoesNotExist:
            logger.error(f"[TASK][REPORT] ReportJob {job_id} no encontrado.")
            return

        job.status = 'PROCESSING'
        job.save()

        survey = job.survey
        metadata = job.metadata or {}
        filters = metadata.get('filters', {})

        qs = SurveyResponse.objects.filter(survey=survey)
        start = filters.get('start_date')
        end = filters.get('end_date')
        
        if start or end:
            qs, _ = DateFilterHelper.apply_filters(qs, start, end)

        analysis_result = SurveyAnalysisService.get_analysis_data(
            survey, qs, include_charts=True
        )

        file_bytes = None
        file_ext = 'pdf'
        
        if job.report_type == 'PDF':
            include_charts_filter = filters.get('include_charts') in [True, 'on', 'true']
            include_table_filter = filters.get('include_table') in [True, 'on', 'true']
            include_kpis_filter = filters.get('include_kpis') in [True, 'on', 'true']

            file_bytes = PDFReportGenerator.generate_report(
                survey=survey,
                analysis_data=analysis_result.get('analysis_data', []),
                nps_data=analysis_result.get('nps_data', {}),
                total_responses=qs.count(),
                kpi_satisfaction_avg=analysis_result.get('kpi_prom_satisfaccion', 0),
                heatmap_image=analysis_result.get('heatmap_image'),
                include_table=include_table_filter,
                include_kpis=include_kpis_filter,
                include_charts=include_charts_filter,
                request=None,
                start_date=start,
                end_date=end
            )
            file_ext = 'pdf'

        elif job.report_type == 'PPTX':
            include_table_filter = filters.get('include_table') in [True, 'on', 'true']
            ppt_io = generate_full_pptx_report(
                survey=survey,
                analysis_data=analysis_result.get('analysis_data', []),
                nps_data=analysis_result.get('nps_data', {}),
                total_responses=qs.count(),
                kpi_satisfaction_avg=analysis_result.get('kpi_prom_satisfaccion', 0),
                heatmap_image=analysis_result.get('heatmap_image'),
                include_table=include_table_filter,
                start_date=start,
                end_date=end
            )
            file_bytes = ppt_io.read()
            file_ext = 'pptx'

        if file_bytes:
            filename = f"Report_{survey.public_id}_{job.id}.{file_ext}"
            public_url, file_path = PDFReportGenerator._save_pdf_to_storage(file_bytes, filename)
            
            job.file_path = file_path
            job.file_url = public_url
            job.status = 'COMPLETED'
            job.completed_at = timezone.now()
            job.save()
            logger.info(f"[TASK][REPORT] Reporte {job.id} generado exitosamente.")
            return f"Reporte {job.id} generado exitosamente: {filename}"
        else:
            raise ValueError("No se generaron bytes para el reporte.")

    except Exception as e:
        logger.error(f"[TASK][REPORT] Error generando reporte {job_id}: {e}", exc_info=True)
        if 'job' in locals():
            job.status = 'FAILED'
            job.metadata['error'] = str(e)
            job.save()
        raise self.retry(exc=e, countdown=10)