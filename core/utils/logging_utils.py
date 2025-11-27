"""
Utilidades de logging para el proyecto.
Incluye decoradores de performance y helpers de logging estructurado.
"""
import time
import logging
import functools
from typing import Any, Callable
from django.conf import settings

# Loggers especializados
performance_logger = logging.getLogger('core.performance')
security_logger = logging.getLogger('core.security')


def log_performance(threshold_ms: float = 1000.0):
    """
    Decorador para loggear el tiempo de ejecución de funciones.
    
    Args:
        threshold_ms: Tiempo en milisegundos. Solo loggea si excede este umbral.
        
    Usage:
        @log_performance(threshold_ms=500)
        def my_slow_function():
            # código
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                elapsed_time = (time.time() - start_time) * 1000  # Convert to ms
                
                if elapsed_time > threshold_ms:
                    performance_logger.warning(
                        f"Slow operation: {func.__module__}.{func.__name__} "
                        f"took {elapsed_time:.2f}ms (threshold: {threshold_ms}ms)"
                    )
                elif settings.DEBUG:
                    performance_logger.debug(
                        f"{func.__module__}.{func.__name__} took {elapsed_time:.2f}ms"
                    )
        
        return wrapper
    return decorator


def log_query_count(func: Callable) -> Callable:
    """
    Decorador para loggear el número de queries ejecutadas por una función.
    Solo funciona en modo DEBUG.
    
    Usage:
        @log_query_count
        def my_db_heavy_function():
            # código con queries
            pass
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        if not settings.DEBUG:
            return func(*args, **kwargs)
        
        from django.db import connection, reset_queries
        
        reset_queries()
        start_queries = len(connection.queries)
        
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            end_queries = len(connection.queries)
            query_count = end_queries - start_queries
            
            if query_count > 10:
                performance_logger.warning(
                    f"High query count: {func.__module__}.{func.__name__} "
                    f"executed {query_count} queries"
                )
            else:
                performance_logger.debug(
                    f"{func.__module__}.{func.__name__} executed {query_count} queries"
                )
    
    return wrapper


def log_user_action(action: str, success: bool = True, **extra_data):
    """
    Loggea acciones de usuario para auditoría.
    
    Args:
        action: Descripción de la acción (ej: 'login', 'create_survey', 'delete_response')
        success: Si la acción fue exitosa
        **extra_data: Datos adicionales para incluir en el log
        
    Usage:
        log_user_action('create_survey', success=True, survey_id=123, user_id=5)
    """
    logger = logging.getLogger('core.security')
    
    log_message = f"User action: {action} - {'SUCCESS' if success else 'FAILED'}"
    
    if extra_data:
        details = ', '.join(f"{k}={v}" for k, v in extra_data.items())
        log_message += f" | {details}"
    
    if success:
        logger.info(log_message)
    else:
        logger.warning(log_message)


def log_security_event(event_type: str, severity: str = 'WARNING', **details):
    """
    Loggea eventos de seguridad.
    
    Args:
        event_type: Tipo de evento (ej: 'unauthorized_access', 'failed_login', 'permission_denied')
        severity: Nivel de severidad ('INFO', 'WARNING', 'ERROR', 'CRITICAL')
        **details: Detalles adicionales del evento
        
    Usage:
        log_security_event(
            'unauthorized_access',
            severity='WARNING',
            user_id=5,
            attempted_resource='survey_123',
            ip_address='192.168.1.1'
        )
    """
    log_message = f"Security event: {event_type}"
    
    if details:
        details_str = ', '.join(f"{k}={v}" for k, v in details.items())
        log_message += f" | {details_str}"
    
    severity_map = {
        'DEBUG': security_logger.debug,
        'INFO': security_logger.info,
        'WARNING': security_logger.warning,
        'ERROR': security_logger.error,
        'CRITICAL': security_logger.critical,
    }
    
    log_func = severity_map.get(severity.upper(), security_logger.warning)
    log_func(log_message)


def log_data_change(model_name: str, operation: str, instance_id: Any, user_id: Any = None, **changes):
    """
    Loggea cambios en datos para auditoría.
    
    Args:
        model_name: Nombre del modelo (ej: 'Encuesta', 'RespuestaPregunta')
        operation: Tipo de operación ('CREATE', 'UPDATE', 'DELETE')
        instance_id: ID de la instancia modificada
        user_id: ID del usuario que realizó el cambio
        **changes: Diccionario de cambios (ej: old_value=X, new_value=Y)
        
    Usage:
        log_data_change(
            'Encuesta',
            'UPDATE',
            instance_id=123,
            user_id=5,
            old_estado='draft',
            new_estado='active'
        )
    """
    logger = logging.getLogger('core')
    
    log_message = f"Data change: {operation} {model_name}(id={instance_id})"
    
    if user_id:
        log_message += f" by user_id={user_id}"
    
    if changes:
        changes_str = ', '.join(f"{k}={v}" for k, v in changes.items())
        log_message += f" | Changes: {changes_str}"
    
    logger.info(log_message)


class StructuredLogger:
    """
    Helper class para logging estructurado con contexto.
    
    Usage:
        logger = StructuredLogger('my_module')
        logger.info('User logged in', user_id=123, ip='192.168.1.1')
    """
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def _format_message(self, message: str, **context) -> str:
        if context:
            context_str = ' | '.join(f"{k}={v}" for k, v in context.items())
            return f"{message} | {context_str}"
        return message
    
    def debug(self, message: str, **context):
        self.logger.debug(self._format_message(message, **context))
    
    def info(self, message: str, **context):
        self.logger.info(self._format_message(message, **context))
    
    def warning(self, message: str, **context):
        self.logger.warning(self._format_message(message, **context))
    
    def error(self, message: str, **context):
        self.logger.error(self._format_message(message, **context))
    
    def exception(self, message: str, **context):
        self.logger.exception(self._format_message(message, **context))
    
    def critical(self, message: str, **context):
        self.logger.critical(self._format_message(message, **context))
