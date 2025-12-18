import logging
import os
import gc
from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import transaction, connection
from django.core.cache import cache

# Monitoreo de recursos
from core.utils.memory_monitor import (
    memory_guard, 
    get_memory_usage, 
    force_garbage_collection,
    log_system_stats
)

# Logger
logger = logging.getLogger(__name__)
User = get_user_model()

@shared_task(bind=True)
@memory_guard(max_memory_mb=500)  # Límite de 500MB por importación
def process_survey_import(self, survey_id: int, file_path: str, filename: str, user_id: int) -> dict:
    """
    Tarea Celery optimizada para importación con monitoreo de memoria.
    Soporta múltiples importaciones simultáneas en 4GB RAM.
    """
    log_system_stats()
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
        
        # Liberar memoria explícitamente (MAGIA NEGRA™)
        gc.collect()
        freed = force_garbage_collection()
        log_system_stats()

@shared_task
def delete_surveys_task(survey_ids: list, user_id: int = None):
    """
    Borrado masivo optimizado usando fast_delete_surveys.
    """
    from surveys.utils.delete_optimizer import fast_delete_surveys
    
    if not survey_ids:
        return {'status': 'SUCCESS', 'deleted': 0}

    logger.info(f"[TASK][DELETE] Iniciando borrado de {len(survey_ids)} encuestas")
    result = fast_delete_surveys(survey_ids)

    # IMPORTANTE: fast_delete_surveys usa SQL directo y no dispara señales.
    # Invalidamos explícitamente el cache del dashboard del usuario para que
    # los contadores se regeneren en la próxima carga.
    if user_id:
        try:
            cache.delete(f"dashboard_data_user_{int(user_id)}")
        except Exception:
            # No bloquear la tarea por problemas de cache
            pass
    
    if result['status'] == 'SUCCESS':
        logger.info(f"[TASK][DELETE] ✅ Completado - {result['deleted']} encuestas eliminadas")
    else:
        logger.error(f"[TASK][DELETE] ❌ Error: {result.get('error', 'Unknown')}")
    
    return result