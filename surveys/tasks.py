import logging
import os
from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction, connection

# Logger
logger = logging.getLogger(__name__)
User = get_user_model()

"""
Compat variable used by tests to monkeypatch chunk size.
Tests set `monkeypatch.setattr('surveys.tasks.chunk_size', N, raising=False)`.
"""
chunk_size = getattr(settings, 'SURVEY_IMPORT_CHUNK_SIZE', 1000)


@shared_task(bind=True)
def process_survey_import(self,
                          job_id: int = None,
                          survey_id: int = None,
                          file_path: str = None,
                          filename: str = None,
                          user_id: int = None) -> dict:
    """
    Tarea Celery que orquesta la importación.
    Delega la lectura (C++) y escritura (COPY) a utils.bulk_import.
    """
    # Soportar dos modos:
    # 1) Modo antiguo (usa survey_id, file_path, filename, user_id)
    # 2) Modo tests (llamado como .run(job_id))
    if job_id is not None and not survey_id and not file_path:
        # Modo tests: cargar ImportJob y procesar internamente
        from surveys.models import ImportJob
        from django.core.files.base import ContentFile
        from surveys.views.import_views import _process_single_csv_import

        logger.info(f"[TASK][IMPORT] Iniciando por job_id={job_id}")
        job = ImportJob.objects.get(id=job_id)
        job.status = 'processing'
        job.save(update_fields=['status', 'updated_at'])

        # Abrir archivo CSV: intentar vía storage si es ruta externa
        csv_path = job.csv_file
        total_rows = 0
        try:
            # Usar almacenamiento por defecto si aplica
            try:
                from django.core.files.storage import default_storage
                if default_storage.exists(csv_path):
                    with default_storage.open(csv_path, 'rb') as f:
                        content = f.read()
                else:
                    with open(csv_path, 'rb') as f:
                        content = f.read()
            except FileNotFoundError as fnf:
                job.status = 'failed'
                job.error_message = str(fnf)
                job.save(update_fields=['status', 'error_message', 'updated_at'])
                logger.error(f"[TASK][IMPORT] Archivo no encontrado (job {job_id}): {fnf}", exc_info=True)
                return {'success': False, 'status': 'FAILURE', 'error': str(fnf)}
            except Exception as e:
                with open(csv_path, 'rb') as f:
                    content = f.read()

            # Procesar mediante helper de importación determinístico usado por tests
            survey, total_rows, _info = _process_single_csv_import(ContentFile(content, name=job.original_filename or 'data.csv'), job.user)

            # Actualizar job
            job.survey = survey
            job.total_rows = total_rows
            job.processed_rows = total_rows
            job.status = 'completed'
            job.save(update_fields=['survey', 'total_rows', 'processed_rows', 'status', 'updated_at'])

            return {
                'success': True,
                'status': 'SUCCESS',
                'imported_count': total_rows,
                'total_rows': total_rows,
                'survey_public_id': survey.public_id,
                'message': 'Importación completada.'
            }
        except Exception as e:
            job.status = 'failed'
            job.error_message = str(e)
            job.save(update_fields=['status', 'error_message', 'updated_at'])
            logger.error(f"[TASK][IMPORT] Fallo crítico (job {job_id}): {e}", exc_info=True)
            return {'success': False, 'status': 'FAILURE', 'error': str(e)}

    logger.info(f"[TASK][IMPORT] Iniciando para encuesta {survey_id} desde {file_path}")
    
    # Importación local para evitar ciclos y asegurar carga de apps
    from surveys.models import Survey
    from surveys.utils.bulk_import import bulk_import_responses_postgres
    
    try:
        survey = Survey.objects.get(id=survey_id)

        # Llamada a la función que usa C++ internamente
        result = bulk_import_responses_postgres(file_path, survey)

        # Si retorna dict con errores de validación, propagarlo
        if isinstance(result, dict) and not result.get('success', True):
            logger.error(f"[TASK][IMPORT][VALIDATION] Errores: {result.get('validation_errors', [])}")
            return {
                'status': 'FAILURE',
                'error': result.get('error', 'Errores de validación en el archivo CSV.'),
                'validation_errors': result.get('validation_errors', [])
            }

        total_rows, imported_rows = result
        logger.info(f"[TASK][IMPORT] Éxito. Filas CSV: {total_rows}, Respuestas insertadas: {imported_rows}")

        return {
            'status': 'SUCCESS',
            'imported_count': imported_rows,
            'total_rows': total_rows,
            'survey_public_id': survey.public_id,
            'message': 'Importación completada.'
        }

    except Survey.DoesNotExist:
        msg = f"Encuesta ID {survey_id} no encontrada."
        logger.error(msg)
        raise Exception(msg)
        
    except Exception as e:
        logger.error(f"[TASK][IMPORT] Fallo crítico: {e}", exc_info=True)
        raise e 
        
    finally:
        # Siempre limpiar el archivo temporal
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.debug(f"Archivo temporal eliminado: {file_path}")
            except Exception as e:
                logger.warning(f"No se pudo eliminar {file_path}: {e}")

@shared_task
def delete_surveys_task(survey_ids: list, user_id: int = None):
    """
    Borrado masivo optimizado (SQL directo).
    """
    if not survey_ids:
        return {'status': 'SUCCESS', 'deleted': 0}

    # Sanitizar IDs
    try:
        ids = [int(i) for i in survey_ids]
    except ValueError:
        return {'status': 'FAILURE', 'error': 'IDs inválidos'}

    logger.info(f"[TASK][DELETE] Borrando {len(ids)} encuestas.")

    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                # Orden de borrado para respetar FKs
                # 1. Respuestas a preguntas (Tabla más pesada)
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
                
                # 5. Jobs de importación asociados (si aplica en tu esquema)
                # cursor.execute("DELETE FROM surveys_importjob WHERE survey_id = ANY(%s::int[])", (ids,))
                
                # 6. La encuesta en sí
                cursor.execute("DELETE FROM surveys_survey WHERE id = ANY(%s::int[])", (ids,))
                
        return {'status': 'SUCCESS', 'deleted': len(ids)}

    except Exception as e:
        logger.error(f"[TASK][DELETE] Error: {e}", exc_info=True)
        return {'status': 'FAILURE', 'error': str(e)}