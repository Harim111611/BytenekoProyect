#!/usr/bin/env python
"""
Script de verificación de optimizaciones para 4GB RAM
"""
import sys
import os
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings.local')
django.setup()

from django.conf import settings
from core.utils.memory_monitor import get_system_stats, log_system_stats
import psutil

def check_settings():
    """Verificar que las configuraciones estén aplicadas"""
    print("\n" + "="*60)
    print("VERIFICACIÓN DE CONFIGURACIONES OPTIMIZADAS")
    print("="*60)
    
    checks = []
    
    # Check chunk sizes
    chunk_size = getattr(settings, 'SURVEY_IMPORT_CHUNK_SIZE', None)
    checks.append(('SURVEY_IMPORT_CHUNK_SIZE', chunk_size, 2500, chunk_size == 2500))
    
    # Check Celery settings
    celery_prefetch = getattr(settings, 'CELERY_WORKER_PREFETCH_MULTIPLIER', None)
    checks.append(('CELERY_WORKER_PREFETCH_MULTIPLIER', celery_prefetch, 2, celery_prefetch == 2))
    
    celery_max_tasks = getattr(settings, 'CELERY_WORKER_MAX_TASKS_PER_CHILD', None)
    checks.append(('CELERY_WORKER_MAX_TASKS_PER_CHILD', celery_max_tasks, 100, celery_max_tasks == 100))
    
    # Check database settings
    db_conn_max_age = settings.DATABASES['default'].get('CONN_MAX_AGE', None)
    checks.append(('DB CONN_MAX_AGE', db_conn_max_age, 300, db_conn_max_age == 300))
    
    # Check cache settings
    cache_backend = settings.CACHES['default']['BACKEND']
    is_redis = 'redis' in cache_backend.lower()
    checks.append(('Cache Backend (Redis)', cache_backend, 'django_redis', is_redis))
    
    # Print results
    print(f"\n{'Setting':<35} {'Current':<20} {'Expected':<15} {'Status'}")
    print("-"*80)
    
    all_ok = True
    for name, current, expected, is_ok in checks:
        status = "✓ OK" if is_ok else "✗ FAIL"
        all_ok = all_ok and is_ok
        print(f"{name:<35} {str(current):<20} {str(expected):<15} {status}")
    
    return all_ok


def check_system_resources():
    """Verificar recursos del sistema"""
    print("\n" + "="*60)
    print("RECURSOS DEL SISTEMA")
    print("="*60 + "\n")
    
    stats = get_system_stats()
    
    print(f"Memoria Total:     {stats['memory_total_mb']:.0f} MB")
    print(f"Memoria Usada:     {stats['memory_used_mb']:.0f} MB ({stats['memory_percent']:.1f}%)")
    print(f"Memoria Disponible: {stats['memory_available_mb']:.0f} MB")
    print(f"Proceso Python:    {stats['process_memory_mb']:.1f} MB")
    print(f"CPU:               {stats['cpu_percent']:.1f}%")
    
    # Warnings
    if stats['memory_total_mb'] < 4000:
        print(f"\n⚠️  WARNING: Sistema tiene menos de 4GB RAM ({stats['memory_total_mb']:.0f}MB)")
    
    if stats['memory_percent'] > 90:
        print(f"\n⚠️  WARNING: Memoria del sistema al {stats['memory_percent']:.1f}%")
    
    return stats


def check_docker_containers():
    """Verificar que los contenedores estén corriendo"""
    print("\n" + "="*60)
    print("CONTENEDORES DOCKER")
    print("="*60 + "\n")
    
    try:
        import subprocess
        result = subprocess.run(
            ['docker', 'ps', '--format', 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'],
            capture_output=True,
            text=True
        )
        print(result.stdout)
        
        # Check expected containers
        expected = ['byteneko_db', 'byteneko_redis', 'byteneko_app', 'byteneko_celery']
        running = result.stdout
        
        for container in expected:
            if container in running:
                print(f"✓ {container} está corriendo")
            else:
                print(f"✗ {container} NO está corriendo")
        
    except Exception as e:
        print(f"No se pudo verificar Docker: {e}")


def main():
    print("\n🚀 ByteNeko - Verificación de Optimizaciones para 4GB RAM\n")
    
    # Run checks
    settings_ok = check_settings()
    stats = check_system_resources()
    check_docker_containers()
    
    # Summary
    print("\n" + "="*60)
    print("RESUMEN")
    print("="*60 + "\n")
    
    if settings_ok:
        print("✓ Todas las configuraciones están optimizadas correctamente")
    else:
        print("✗ Algunas configuraciones necesitan ajustes")
    
    print(f"\nMemoria disponible: {stats['memory_available_mb']:.0f}MB")
    print(f"Uso actual: {stats['memory_used_mb']:.0f}MB ({stats['memory_percent']:.1f}%)")
    
    if stats['memory_available_mb'] > 1000:
        print("\n✓ Hay suficiente memoria disponible para operación normal")
    else:
        print("\n⚠️  Poca memoria disponible, considere liberar recursos")
    
    print("\n" + "="*60)
    print("Para monitorear en tiempo real:")
    print("  docker stats")
    print("  docker logs byteneko_celery -f | grep MEMORY")
    print("="*60 + "\n")


if __name__ == '__main__':
    main()
