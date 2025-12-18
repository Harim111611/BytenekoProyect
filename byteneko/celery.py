"""
Celery configuration for ByteNeko project.
"""

from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from celery.schedules import crontab

# Set default Django settings module / environment
os.environ.setdefault('DJANGO_ENV', os.environ.get('DJANGO_ENV', 'local'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings.base')

app = Celery('byteneko')

# Load configuration from Django settings with CELERY_ namespace
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

# Worker configuration (se puede sobrescribir en línea de comandos)
# Por defecto usa CELERY_WORKER_CONCURRENCY del settings (4 workers)
# Para cambiar: celery -A byteneko worker --concurrency=8

# Celery Beat schedule (periodic tasks)
app.conf.beat_schedule = {
    # Clean old survey responses (older than 2 years)
    'cleanup-old-responses': {
        'task': 'surveys.tasks.cleanup_old_responses',
        'schedule': crontab(hour=3, minute=0),  # Daily at 3 AM
    },
    # Generate monthly reports
    'generate-monthly-reports': {
        'task': 'surveys.tasks.generate_monthly_reports',
        'schedule': crontab(day_of_month=1, hour=4, minute=0),  # First day of month at 4 AM
    },
    # Clean expired cache entries
    'cleanup-cache': {
        'task': 'surveys.tasks.cleanup_cache',
        'schedule': crontab(hour=2, minute=30),  # Daily at 2:30 AM
    },
}

# ============================================================
# OPTIMIZACIONES PARA 4GB RAM Y MÚLTIPLES USUARIOS
# ============================================================

# Task priorities
app.conf.task_default_priority = 5
app.conf.task_inherit_parent_priority = True

# Optimizaciones de memoria y concurrencia
app.conf.worker_prefetch_multiplier = 2  # Prefetch 2 tareas por worker
app.conf.worker_max_tasks_per_child = 100  # Reciclar workers después de 100 tareas
app.conf.task_acks_late = True  # Ack después de completar, no al recibir
app.conf.worker_disable_rate_limits = True  # Sin rate limits para máximo throughput

# Timeouts optimizados para importaciones grandes
app.conf.task_soft_time_limit = 1500  # 25 minutos soft limit
app.conf.task_time_limit = 1800  # 30 minutos hard limit
app.conf.task_reject_on_worker_lost = True

# Compresión y serialización optimizada
app.conf.task_compression = 'gzip'
app.conf.result_compression = 'gzip'
app.conf.task_serializer = 'json'
app.conf.result_serializer = 'json'
app.conf.accept_content = ['json']

# Optimización de resultados
app.conf.result_expires = 3600  # Resultados expiran en 1 hora
app.conf.result_backend_transport_options = {
    'master_name': 'mymaster',
    'socket_keepalive': True,
    'socket_keepalive_options': {
        1: 1,  # TCP_KEEPIDLE
        2: 1,  # TCP_KEEPINTVL
        3: 3,  # TCP_KEEPCNT
    },
}

# Queue routing para múltiples importaciones simultáneas
app.conf.task_routes = {
    'surveys.tasks.process_survey_import': {
        'queue': 'celery',
        'routing_key': 'import',
        'priority': 8,  # Alta prioridad
    },
    'surveys.tasks.delete_surveys_task': {
        'queue': 'celery',
        'routing_key': 'delete',
        'priority': 5,
    },
    'surveys.tasks.generate_pdf_report': {
        'queue': 'celery',
        'routing_key': 'reports',
        'priority': 3,
    },
}

# Alinear la cola por defecto con el worker actual
app.conf.task_default_queue = 'celery'
