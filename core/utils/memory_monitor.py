"""
Monitoreo de recursos optimizado para 4GB RAM
"""
import psutil
import logging
from functools import wraps
from django.conf import settings

logger = logging.getLogger(__name__)

# Límites de memoria (en MB)
MEMORY_WARNING_THRESHOLD = 3200  # Advertencia al 80% de 4GB
MEMORY_CRITICAL_THRESHOLD = 3600  # Crítico al 90% de 4GB


def get_memory_usage():
    """Obtiene el uso de memoria del proceso actual"""
    process = psutil.Process()
    mem_info = process.memory_info()
    mem_mb = mem_info.rss / (1024 * 1024)
    return mem_mb


def check_memory_limits():
    """Verifica si se están alcanzando límites de memoria"""
    mem_mb = get_memory_usage()
    
    if mem_mb > MEMORY_CRITICAL_THRESHOLD:
        logger.critical(f"[MEMORY][CRITICAL] Uso de memoria: {mem_mb:.1f}MB (>{MEMORY_CRITICAL_THRESHOLD}MB)")
        return 'critical'
    elif mem_mb > MEMORY_WARNING_THRESHOLD:
        logger.warning(f"[MEMORY][WARNING] Uso de memoria: {mem_mb:.1f}MB (>{MEMORY_WARNING_THRESHOLD}MB)")
        return 'warning'
    return 'ok'


def memory_guard(max_memory_mb=None):
    """
    Decorator para monitorear memoria en funciones críticas
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Memoria inicial
            mem_before = get_memory_usage()
            logger.info(f"[MEMORY][{func.__name__}] Inicio: {mem_before:.1f}MB")
            
            # Verificar límites antes de ejecutar
            status = check_memory_limits()
            if status == 'critical':
                raise MemoryError(f"Memoria crítica alcanzada: {mem_before:.1f}MB")
            
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                # Memoria final
                mem_after = get_memory_usage()
                mem_delta = mem_after - mem_before
                logger.info(f"[MEMORY][{func.__name__}] Fin: {mem_after:.1f}MB (Δ{mem_delta:+.1f}MB)")
                
                # Verificar si se excedió el límite
                if max_memory_mb and mem_delta > max_memory_mb:
                    logger.warning(f"[MEMORY][{func.__name__}] Excedió límite: {mem_delta:.1f}MB > {max_memory_mb}MB")
        
        return wrapper
    return decorator


def force_garbage_collection():
    """Fuerza recolección de basura y retorna memoria liberada"""
    import gc
    
    mem_before = get_memory_usage()
    gc.collect()
    mem_after = get_memory_usage()
    freed_mb = mem_before - mem_after
    
    if freed_mb > 0:
        logger.info(f"[MEMORY][GC] Liberados {freed_mb:.1f}MB")
    
    return freed_mb


def get_system_stats():
    """Obtiene estadísticas del sistema completo"""
    mem = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=1)
    
    return {
        'memory_total_mb': mem.total / (1024 * 1024),
        'memory_available_mb': mem.available / (1024 * 1024),
        'memory_used_mb': mem.used / (1024 * 1024),
        'memory_percent': mem.percent,
        'cpu_percent': cpu_percent,
        'process_memory_mb': get_memory_usage(),
    }


def log_system_stats():
    """Log de estadísticas del sistema"""
    stats = get_system_stats()
    logger.info(
        f"[SYSTEM] RAM: {stats['memory_used_mb']:.0f}/{stats['memory_total_mb']:.0f}MB ({stats['memory_percent']:.1f}%) "
        f"| Proceso: {stats['process_memory_mb']:.1f}MB "
        f"| CPU: {stats['cpu_percent']:.1f}%"
    )
