"""
Optimización de eliminaciones para evitar lentitud por CASCADE y señales.
"""
import logging
from django.db import connection, transaction
from typing import List

logger = logging.getLogger('surveys')


def fast_delete_surveys(survey_ids: List[int]) -> dict:
    """
    Eliminación ultra-rápida usando SQL directo.
    
    Beneficios:
    - 100-1000x más rápido que .delete() de Django
    - No carga objetos en memoria
    - No dispara señales (post_delete, etc)
    - Respeta relaciones FK con DELETE manual en orden correcto
    
    Args:
        survey_ids: Lista de IDs de encuestas a eliminar
        
    Returns:
        dict con 'status', 'deleted' y/o 'error'
    """
    if not survey_ids:
        return {'status': 'SUCCESS', 'deleted': 0}

    # Sanitizar IDs
    try:
        ids = [int(i) for i in survey_ids]
    except (ValueError, TypeError):
        return {'status': 'FAILURE', 'error': 'IDs inválidos'}

    logger.info(f"[DELETE][FAST] Eliminando {len(ids)} encuestas con SQL directo")

    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                # ORDEN CRÍTICO: de hijos a padres para evitar errores FK
                
                # 1. QuestionResponse (tabla más grande, respuestas individuales)
                cursor.execute("""
                    DELETE FROM surveys_questionresponse 
                    WHERE survey_response_id IN (
                        SELECT id FROM surveys_surveyresponse WHERE survey_id = ANY(%s::int[])
                    )
                """, (ids,))
                qr_deleted = cursor.rowcount
                logger.info(f"[DELETE][FAST] Eliminadas {qr_deleted} respuestas individuales")
                
                # 2. SurveyResponse (respuestas completas)
                cursor.execute(
                    "DELETE FROM surveys_surveyresponse WHERE survey_id = ANY(%s::int[])", 
                    (ids,)
                )
                sr_deleted = cursor.rowcount
                logger.info(f"[DELETE][FAST] Eliminadas {sr_deleted} respuestas de encuesta")
                
                # 3. AnalysisSegment (segmentos de análisis)
                cursor.execute(
                    "DELETE FROM surveys_analysissegment WHERE survey_id = ANY(%s::int[])", 
                    (ids,)
                )
                as_deleted = cursor.rowcount
                logger.info(f"[DELETE][FAST] Eliminados {as_deleted} segmentos de análisis")
                
                # 4. AnswerOption (opciones de preguntas)
                cursor.execute("""
                    DELETE FROM surveys_answeroption 
                    WHERE question_id IN (
                        SELECT id FROM surveys_question WHERE survey_id = ANY(%s::int[])
                    )
                """, (ids,))
                ao_deleted = cursor.rowcount
                logger.info(f"[DELETE][FAST] Eliminadas {ao_deleted} opciones de respuesta")
                
                # 5. Question (preguntas)
                cursor.execute(
                    "DELETE FROM surveys_question WHERE survey_id = ANY(%s::int[])", 
                    (ids,)
                )
                q_deleted = cursor.rowcount
                logger.info(f"[DELETE][FAST] Eliminadas {q_deleted} preguntas")
                
                # 6. ImportJob (opcional, jobs de importación)
                cursor.execute(
                    "DELETE FROM surveys_importjob WHERE survey_id = ANY(%s::int[])", 
                    (ids,)
                )
                ij_deleted = cursor.rowcount
                logger.info(f"[DELETE][FAST] Eliminados {ij_deleted} import jobs")
                
                # 7. Survey (finalmente, las encuestas)
                cursor.execute(
                    "DELETE FROM surveys_survey WHERE id = ANY(%s::int[])", 
                    (ids,)
                )
                s_deleted = cursor.rowcount
                logger.info(f"[DELETE][FAST] Eliminadas {s_deleted} encuestas")
                
        logger.info(f"[DELETE][FAST] ✅ Completado - Total: {s_deleted} encuestas + {qr_deleted + sr_deleted} respuestas")
        return {
            'status': 'SUCCESS', 
            'deleted': s_deleted,
            'details': {
                'surveys': s_deleted,
                'responses': sr_deleted,
                'question_responses': qr_deleted,
                'analysis_segments': as_deleted,
                'questions': q_deleted,
                'options': ao_deleted,
                'import_jobs': ij_deleted
            }
        }

    except Exception as e:
        logger.error(f"[DELETE][FAST] ❌ Error: {e}", exc_info=True)
        return {'status': 'FAILURE', 'error': str(e)}


def fast_delete_single_survey(survey_id: int) -> dict:
    """Conveniencia para eliminar una sola encuesta."""
    return fast_delete_surveys([survey_id])
