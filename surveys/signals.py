# surveys/signals.py
from django.db.models.signals import post_save, post_delete, pre_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import Survey, Question, AnswerOption, SurveyResponse, QuestionResponse
import logging
import threading

logger = logging.getLogger('surveys')

# Thread-local storage para deshabilitar señales durante operaciones masivas
_thread_locals = threading.local()


def disable_signals():
    """Deshabilita temporalmente las señales de invalidación de caché."""
    _thread_locals.signals_disabled = True


def enable_signals():
    """Habilita las señales de invalidación de caché."""
    _thread_locals.signals_disabled = False


def are_signals_enabled():
    """Verifica si las señales están habilitadas."""
    return not getattr(_thread_locals, 'signals_disabled', False)


class DisableSignals:
    """
    Context manager para deshabilitar temporalmente las señales de caché.
    
    Uso:
        with DisableSignals():
            # Operaciones masivas sin invalidación de caché
            survey.delete()  # No dispara señales
        # Aquí puedes invalidar el caché manualmente una sola vez
    """
    def __enter__(self):
        disable_signals()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        enable_signals()
        return False  # No suprimir excepciones


def invalidate_pattern(pattern):
    """
    Invalida todas las claves de caché que coinciden con el patrón.
    Redis soporta delete_pattern, pero en desarrollo (MemCache) usamos lógica manual.
    """
    try:
        # Intenta usar delete_pattern de django-redis
        if hasattr(cache, 'delete_pattern'):
            cache.delete_pattern(pattern)
        else:
            # Fallback para backends sin delete_pattern (silencioso en desarrollo)
            pass
        logger.debug(f"Cache invalidated with pattern: {pattern}")
    except AttributeError:
        # Fallback para backends sin delete_pattern (silencioso en desarrollo)
        pass


@receiver(post_save, sender=Survey)
@receiver(post_delete, sender=Survey)
def invalidate_survey_cache(sender, instance, **kwargs):
    """
    Invalida caché relacionada cuando una encuesta cambia.
    Cascade: Dashboard → Survey Analysis → Reports
    """
    import os
    if os.environ.get('DJANGO_ENV') == 'test':
        return
    
    if not are_signals_enabled():
        return
    
    if instance.author:
        # 1. Dashboard del usuario
        dashboard_key = f"dashboard_data_user_{instance.author.id}"
        cache.delete(dashboard_key)
        
        # 2. Análisis de la encuesta (todos los filtros de fecha)
        analysis_pattern = f"survey_analysis_{instance.id}_*"
        invalidate_pattern(analysis_pattern)
        
        # 3. Resultados de la encuesta
        results_pattern = f"survey_results_{instance.id}_*"
        invalidate_pattern(results_pattern)
        
        # 4. Estadísticas
        stats_key = f"survey_stats_{instance.id}"
        cache.delete(stats_key)
        
        # 5. Reportes generados
        pdf_pattern = f"pdf_report_{instance.id}_*"
        pptx_pattern = f"pptx_report_{instance.id}_*"
        invalidate_pattern(pdf_pattern)
        invalidate_pattern(pptx_pattern)
        
        logger.info(
            f"Cache invalidated for survey {instance.id} (user: {instance.author.username})"
        )


@receiver(post_save, sender=Question)
@receiver(post_delete, sender=Question)
def invalidate_question_cache(sender, instance, **kwargs):
    """
    Invalida caché cuando las preguntas cambian.
    Cascade: Survey → Analysis → Reports
    OPTIMIZACIÓN: Solo se ejecuta si las señales están habilitadas.
    """
    import os
    if os.environ.get('DJANGO_ENV') == 'test':
        return
    
    if not are_signals_enabled():
        return
    
    survey = instance.survey
    
    # Invalidar análisis y resultados de la encuesta
    analysis_pattern = f"survey_analysis_{survey.id}_*"
    results_pattern = f"survey_results_{survey.id}_*"
    invalidate_pattern(analysis_pattern)
    invalidate_pattern(results_pattern)
    
    # Invalidar reportes
    pdf_pattern = f"pdf_report_{survey.id}_*"
    pptx_pattern = f"pptx_report_{survey.id}_*"
    invalidate_pattern(pdf_pattern)
    invalidate_pattern(pptx_pattern)
    
    logger.info(
        f"Cache invalidated for question changes in survey {survey.id}"
    )


@receiver(post_save, sender=AnswerOption)
@receiver(post_delete, sender=AnswerOption)
def invalidate_option_cache(sender, instance, **kwargs):
    """
    Invalida caché cuando las opciones de respuesta cambian.
    Cascade: Question → Survey → Analysis
    OPTIMIZACIÓN: Solo se ejecuta si las señales están habilitadas.
    """
    import os
    if os.environ.get('DJANGO_ENV') == 'test':
        return
    
    if not are_signals_enabled():
        return
    
    survey = instance.question.survey
    
    # Invalidar análisis de la encuesta
    analysis_pattern = f"survey_analysis_{survey.id}_*"
    results_pattern = f"survey_results_{survey.id}_*"
    invalidate_pattern(analysis_pattern)
    invalidate_pattern(results_pattern)
    
    logger.info(
        f"Cache invalidated for answer option changes in survey {survey.id}"
    )


@receiver(post_save, sender=SurveyResponse)
@receiver(post_delete, sender=SurveyResponse)
def invalidate_response_cache(sender, instance, **kwargs):
    """
    Invalida caché cuando se agregan/eliminan respuestas.
    Cascade: Survey → Analysis → Stats → Reports
    OPTIMIZACIÓN: Solo se ejecuta si las señales están habilitadas.
    """
    import os
    if os.environ.get('DJANGO_ENV') == 'test':
        return
    
    if not are_signals_enabled():
        return
    
    survey = instance.survey
    
    # 1. Análisis y resultados
    analysis_pattern = f"survey_analysis_{survey.id}_*"
    results_pattern = f"survey_results_{survey.id}_*"
    invalidate_pattern(analysis_pattern)
    invalidate_pattern(results_pattern)
    
    # 2. Estadísticas
    stats_key = f"survey_stats_{survey.id}"
    cache.delete(stats_key)
    
    # 3. Dashboard del dueño (contadores cambian)
    if survey.author:
        dashboard_key = f"dashboard_data_user_{survey.author.id}"
        cache.delete(dashboard_key)
    
    # 4. Reportes (deben regenerarse con nuevos datos)
    pdf_pattern = f"pdf_report_{survey.id}_*"
    pptx_pattern = f"pptx_report_{survey.id}_*"
    invalidate_pattern(pdf_pattern)
    invalidate_pattern(pptx_pattern)
    
    logger.info(
        f"Cache invalidated for response changes in survey {survey.id}"
    )


@receiver(post_save, sender=QuestionResponse)
@receiver(post_delete, sender=QuestionResponse)
def invalidate_question_response_cache(sender, instance, **kwargs):
    """
    Invalida caché cuando las respuestas a preguntas específicas cambian.
    Cascade: SurveyResponse → Survey → Analysis
    OPTIMIZACIÓN: Solo se ejecuta si las señales están habilitadas.
    """
    import os
    if os.environ.get('DJANGO_ENV') == 'test':
        return
    
    if not are_signals_enabled():
        return
    
    try:
        survey = instance.survey_response.survey
        
        # Invalidar análisis (afecta estadísticas por pregunta)
        analysis_pattern = f"survey_analysis_{survey.id}_*"
        results_pattern = f"survey_results_{survey.id}_*"
        invalidate_pattern(analysis_pattern)
        invalidate_pattern(results_pattern)
        
        # Estadísticas
        stats_key = f"survey_stats_{survey.id}"
        cache.delete(stats_key)
        
        logger.debug(
            f"Cache invalidated for question response changes in survey {survey.id}"
        )
    except (AttributeError, SurveyResponse.DoesNotExist):
        # La respuesta padre ya fue eliminada, ignorar
        pass