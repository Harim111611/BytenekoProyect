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

def _process_survey_import_impl(survey_id: int, file_path: str, filename: str, user_id: int) -> dict:
    """
    Implementación interna de la importación (no task). Se puede llamar
    desde el task o de forma síncrona en tests.
    """
    logger.info(f"[IMPORT] Iniciando para encuesta {survey_id} desde {file_path}")

    # Importación local para evitar ciclos y asegurar carga de apps
    from surveys.models import Survey
    from surveys.utils.bulk_import import bulk_import_responses_postgres

    survey = Survey.objects.get(id=survey_id)
    total_rows, imported_rows = bulk_import_responses_postgres(file_path, survey)

    logger.info(f"[IMPORT] Éxito. Filas CSV: {total_rows}, Respuestas insertadas: {imported_rows}")
    return {
        'status': 'SUCCESS',
        'imported_count': imported_rows,
        'total_rows': total_rows,
        'survey_id': survey_id,
    }


@shared_task(bind=True)
def process_survey_import(self, job_id: int):
    """
    Task Celery compatible con la API histórica: recibe `ImportJob.id`,
    recupera los datos y delega a la implementación interna.
    """
    from surveys.models import ImportJob

    try:
        job = ImportJob.objects.get(id=job_id)
    except ImportJob.DoesNotExist:
        logger.error(f"ImportJob {job_id} no encontrado")
        return {'status': 'FAILURE', 'error': 'job_not_found'}

    try:
        result = _process_survey_import_impl(job.survey_id, job.csv_file, getattr(job, 'original_filename', ''), job.user_id)
        return result
    except Exception as e:
        logger.exception(f"[TASK][IMPORT] Error crítico: {e}")
        # Reintentar si es un error temporal
        raise self.retry(exc=e, countdown=10)

@shared_task(bind=True)
def bulk_delete_surveys(self, ids):
    """
    Elimina encuestas masivamente usando SQL crudo para máxima velocidad.
    Evita la sobrecarga del ORM de Django en eliminaciones en cascada.
    """
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                # 1. Respuestas a preguntas (la tabla más grande)
                cursor.execute("""
                    DELETE FROM surveys_questionresponse 
                    WHERE survey_response_id IN (
                        SELECT id FROM surveys_surveyresponse WHERE survey_id = ANY(%s::int[])
                    )
                """, (ids,))
                
                # 2. Respuestas de encuesta
                cursor.execute("DELETE FROM surveys_surveyresponse WHERE survey_id = ANY(%s::int[])", (ids,))
                
                # 3. Opciones de respuesta (definición)
                cursor.execute("""
                    DELETE FROM surveys_answeroption 
                    WHERE question_id IN (
                        SELECT id FROM surveys_question WHERE survey_id = ANY(%s::int[])
                    )
                """, (ids,))
                
                # 4. Preguntas
                cursor.execute("DELETE FROM surveys_question WHERE survey_id = ANY(%s::int[])", (ids,))
                
                # 5. Jobs de importación y Reportes asociados
                # Es buena práctica limpiar también los ReportJobs y ImportJobs si existen
                cursor.execute("DELETE FROM surveys_importjob WHERE survey_id = ANY(%s::int[])", (ids,))
                cursor.execute("DELETE FROM core_reportjob WHERE survey_id = ANY(%s::int[])", (ids,))
                
                # 6. La encuesta en sí
                cursor.execute("DELETE FROM surveys_survey WHERE id = ANY(%s::int[])", (ids,))
                
        return {'status': 'SUCCESS', 'deleted': len(ids)}

    except Exception as e:
        logger.error(f"[TASK][DELETE] Error: {e}", exc_info=True)
        return {'status': 'FAILURE', 'error': str(e)}

@shared_task(bind=True, max_retries=3)
def generate_report_task(self, job_id):
    """
    Tarea Celery para generar reportes PDF/PPTX en segundo plano.
    Recibe el ID del ReportJob, genera el archivo y actualiza el registro.
    """
    # Importaciones locales para evitar conflictos circulares
    from core.models_reports import ReportJob
    from surveys.models import Survey, SurveyResponse
    from core.reports.pdf_generator import PDFReportGenerator 
    from core.reports.pptx_generator import generate_full_pptx_report
    from core.utils.helpers import DateFilterHelper
    from core.services.survey_analysis import SurveyAnalysisService

    try:
        # 1. Obtener el trabajo y marcar como procesando
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

        # 2. Reconstruir el QuerySet basado en los filtros guardados
        qs = SurveyResponse.objects.filter(survey=survey)
        start = filters.get('start_date')
        end = filters.get('end_date')
        
        if start or end:
            qs, _ = DateFilterHelper.apply_filters(qs, start, end)

        # 3. Obtener los datos del análisis (usando el servicio optimizado)
        # include_charts=True es crucial para que se generen las imágenes
        analysis_result = SurveyAnalysisService.get_analysis_data(
            survey, qs, include_charts=True
        )

        file_bytes = None
        file_ext = 'pdf'
        
        # 4. Generar el archivo según el tipo
        if job.report_type == 'PDF':
            # Convertir 'on'/'off' strings a booleanos
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
                request=None, # No hay request en una tarea asíncrona
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

        # 5. Guardar el archivo generado
        if file_bytes:
            filename = f"Report_{survey.public_id}_{job.id}.{file_ext}"
            
            # Reutilizamos el método helper del generador para guardar
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
        # Reintentar en caso de error temporal
        raise self.retry(exc=e, countdown=10)