"""
surveys/tasks.py
Tareas asíncronas para reportes, importaciones y mantenimiento.
"""
import logging
import os
from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import transaction, connection
from django.utils import timezone

# Logger
logger = logging.getLogger(__name__)
User = get_user_model()

@shared_task(bind=True)
def process_survey_import(self, job_id: int):
    """
    Procesa un ImportJob en background.
    Actualiza el estado del job en la base de datos para el polling del frontend.
    """
    from surveys.models import ImportJob, Survey
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

        # 2. Ejecutar lógica de importación
        # Si la encuesta fue borrada mientras tanto, esto fallará, lo cual es correcto
        if not job.survey:
             raise ValueError("La encuesta asociada fue eliminada.")

        # Usar el path guardado en el Job
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
        
        # 4. Actualizar Job con error
        job.status = 'failed'
        job.error_log = str(e)
        job.error_message = str(e)[:100] # Mensaje corto para UI
        job.save(update_fields=['status', 'error_log', 'error_message', 'updated_at'])
        
        # Reintentar solo si es un error de conexión o bloqueo temporal, no de lógica
        # raise self.retry(exc=e, countdown=10) # Descomentar si se desea retry
        return {'status': 'FAILURE', 'error': str(e)}

@shared_task(bind=True)
def bulk_delete_surveys(self, ids):
    """
    Elimina encuestas masivamente usando SQL crudo para máxima velocidad.
    """
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                # 1. Respuestas a preguntas
                cursor.execute("""
                    DELETE FROM surveys_questionresponse 
                    WHERE survey_response_id IN (
                        SELECT id FROM surveys_surveyresponse WHERE survey_id = ANY(%s::int[])
                    )
                """, (ids,))
                
                # 2. Respuestas de encuesta
                cursor.execute("DELETE FROM surveys_surveyresponse WHERE survey_id = ANY(%s::int[])", (ids,))
                
                # 3. Opciones de respuesta
                cursor.execute("""
                    DELETE FROM surveys_answeroption 
                    WHERE question_id IN (
                        SELECT id FROM surveys_question WHERE survey_id = ANY(%s::int[])
                    )
                """, (ids,))
                
                # 4. Preguntas
                cursor.execute("DELETE FROM surveys_question WHERE survey_id = ANY(%s::int[])", (ids,))
                
                # 5. Jobs asociados
                cursor.execute("DELETE FROM surveys_importjob WHERE survey_id = ANY(%s::int[])", (ids,))
                cursor.execute("DELETE FROM core_reportjob WHERE survey_id = ANY(%s::int[])", (ids,))
                
                # 6. La encuesta
                cursor.execute("DELETE FROM surveys_survey WHERE id = ANY(%s::int[])", (ids,))
                
        return {'status': 'SUCCESS', 'deleted': len(ids)}

    except Exception as e:
        logger.error(f"[TASK][DELETE] Error: {e}", exc_info=True)
        return {'status': 'FAILURE', 'error': str(e)}

@shared_task(bind=True, max_retries=3)
def generate_report_task(self, job_id):
    # ... (El resto de la tarea de reportes se mantiene igual que en tu archivo original)
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