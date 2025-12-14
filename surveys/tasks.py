import logging
import os
from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import transaction, connection

# Logger
logger = logging.getLogger(__name__)
User = get_user_model()

@shared_task(bind=True)
def process_survey_import(self, survey_id: int, file_path: str, filename: str, user_id: int) -> dict:
    """
    Tarea Celery que orquesta la importación.
    Delega la lectura (C++) y escritura (COPY) a utils.bulk_import.
    """
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