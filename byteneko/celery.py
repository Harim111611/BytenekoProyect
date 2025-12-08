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

# Celery task priorities
app.conf.task_default_priority = 5
app.conf.task_inherit_parent_priority = True

# Queue routing - TODAS las tareas van a la cola por defecto
# Si quieres usar colas específicas, debes iniciar workers con -Q nombre_cola
app.conf.task_routes = {
    # Por ahora comentadas para que todas vayan a la cola por defecto
    # 'surveys.tasks.generate_pdf_report': {'queue': 'reports'},
    # 'surveys.tasks.generate_pptx_report': {'queue': 'reports'},
    # 'surveys.tasks.generate_chart_*': {'queue': 'charts'},
    # 'surveys.tasks.process_survey_import': {'queue': 'imports'},
}

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task to test Celery configuration."""
    print(f'Request: {self.request!r}')
