from asgiref.sync import sync_to_async
import asyncio
async def log_user_action_async(action: str, success: bool = True, **extra_data):
    await sync_to_async(log_user_action)(action, success, **extra_data)

async def log_security_event_async(event_type: str, severity: str = 'WARNING', **details):
    await sync_to_async(log_security_event)(event_type, severity, **details)

async def log_data_change_async(model_name: str, operation: str, instance_id: any, user_id: any = None, **changes):
    await sync_to_async(log_data_change)(model_name, operation, instance_id, user_id, **changes)
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
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed_time = (time.time() - start_time) * 1000
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
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        if not settings.DEBUG:
            return func(*args, **kwargs)
        
        from django.db import connection, reset_queries
        reset_queries()
        start_queries = len(connection.queries)
        try:
            return func(*args, **kwargs)
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
    logger = logging.getLogger('core')
    log_message = f"Data change: {operation} {model_name}(id={instance_id})"
    if user_id:
        log_message += f" by user_id={user_id}"
    if changes:
        changes_str = ', '.join(f"{k}={v}" for k, v in changes.items())
        log_message += f" | Changes: {changes_str}"
    logger.info(log_message)


class StructuredLogger:
    async def debug_async(self, message: str, *args, **context):
        await sync_to_async(self.debug)(message, *args, **context)

    async def info_async(self, message: str, *args, **context):
        await sync_to_async(self.info)(message, *args, **context)

    async def warning_async(self, message: str, *args, **context):
        await sync_to_async(self.warning)(message, *args, **context)

    async def error_async(self, message: str, *args, **context):
        await sync_to_async(self.error)(message, *args, **context)

    async def exception_async(self, message: str, *args, **context):
        await sync_to_async(self.exception)(message, *args, **context)

    async def critical_async(self, message: str, *args, **context):
        await sync_to_async(self.critical)(message, *args, **context)
    """
    Helper class para logging estructurado con contexto.
    Soporta *args y kwargs estándar de logging (exc_info, extra, stack_info).
    """
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def _format_message(self, message: str, **context) -> str:
        if context:
            # Convertimos el contexto a string para agregarlo al mensaje
            context_str = ' | '.join(f"{k}={v}" for k, v in context.items())
            return f"{message} | {context_str}"
        return message

    def _log(self, level_func, message, args, kwargs):
        # Extraer argumentos reservados de logging estándar
        exc_info = kwargs.pop('exc_info', None)
        stack_info = kwargs.pop('stack_info', None)
        extra = kwargs.pop('extra', None)
        
        # El resto de kwargs son contexto para el mensaje visual
        formatted_msg = self._format_message(str(message), **kwargs)
        
        # Llamar al logger nativo con los argumentos correctos
        level_func(formatted_msg, *args, exc_info=exc_info, stack_info=stack_info, extra=extra)

    def debug(self, message: str, *args, **context):
        self._log(self.logger.debug, message, args, context)
    
    def info(self, message: str, *args, **context):
        self._log(self.logger.info, message, args, context)
    
    def warning(self, message: str, *args, **context):
        self._log(self.logger.warning, message, args, context)
    
    def error(self, message: str, *args, **context):
        self._log(self.logger.error, message, args, context)
    
    def exception(self, message: str, *args, **context):
        # exception() añade exc_info=True automáticamente en el logger nativo
        self._log(self.logger.exception, message, args, context)
    
    def critical(self, message: str, *args, **context):
        self._log(self.logger.critical, message, args, context)