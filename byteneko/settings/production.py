"""
Production settings for ByteNeko project.
Optimized for AWS deployment (ECS/EC2) with Gunicorn (4 workers).
"""

from .base import * # noqa: F401,F403
from decouple import config, Csv
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.redis import RedisIntegration

# Tamaño de chunk para importación masiva (Ajustado para balancear RAM/CPU por worker)
SURVEY_IMPORT_CHUNK_SIZE = 2000 

# ============================================================
# SECURITY SETTINGS
# ============================================================

DEBUG = False

SECRET_KEY = config('SECRET_KEY')

ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())

# HTTPS/SSL Settings (AWS Load Balancer suele manejar SSL, pero Django debe saberlo)
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# HSTS Settings
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Cookie Security
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax' # 'Strict' puede romper flujos de OAuth o enlaces externos a veces
SESSION_COOKIE_AGE = 86400

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Strict'

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# ============================================================
# DATABASE CONFIGURATION - PostgreSQL (AWS RDS)
# ============================================================

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT', default='5432'),
        # Optimización AWS: Menor tiempo de vida de conexión para evitar
        # problemas con re-deployments o escalado de contenedores.
        'CONN_MAX_AGE': 60,  
        'CONN_HEALTH_CHECKS': True,
        'OPTIONS': {
            'connect_timeout': 5,
            # IMPORTANTE: Statement timeout aumentado para tareas pesadas de análisis
            # pero mantenido seguro para evitar bloqueos eternos.
            'options': '-c statement_timeout=60000', 
        },
        'ATOMIC_REQUESTS': True,
    }
}

# ============================================================
# CACHE & CELERY CONFIGURATION - Redis (AWS ElastiCache)
# ============================================================

# Usar una sola variable REDIS_URL para simplificar la configuración en AWS
REDIS_URL = config('REDIS_URL', default='redis://127.0.0.1:6379')

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': f"{REDIS_URL}/1",
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
            # Connection Pool ajustado: 4 workers * 4 threads = ~16 conexiones por contenedor.
            # 50 es suficiente margen de seguridad sin saturar Redis.
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 50,
                'retry_on_timeout': True,
                'health_check_interval': 30,
            },
            'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
        },
        'KEY_PREFIX': 'byteneko',
        'TIMEOUT': 300,
    }
}

SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

CELERY_BROKER_URL = f"{REDIS_URL}/0"
CELERY_RESULT_BACKEND = f"{REDIS_URL}/0"

CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# Worker Optimizations for 4 Workers
CELERY_WORKER_PREFETCH_MULTIPLIER = 1 # Fair dispatch. Evita que un worker acapare tareas largas.
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_TIME_LIMIT = 1800  # 30 min
CELERY_TASK_SOFT_TIME_LIMIT = 1500 # 25 min
CELERY_WORKER_MAX_TASKS_PER_CHILD = 500 # Reiniciar worker frecuentemente para liberar memoria (pandas leaks)

# ============================================================
# STATIC & MEDIA FILES
# ============================================================

STATIC_ROOT = BASE_DIR / 'staticfiles'
STATIC_URL = '/static/'

MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

if config('USE_S3', default=False, cast=bool):
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='us-east-1')
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
    AWS_S3_FILE_OVERWRITE = False
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/'
else:
    MEDIA_ROOT = BASE_DIR / 'media'
    MEDIA_URL = '/media/'

# ============================================================
# LOGGING & SENTRY
# ============================================================

# ... (Configuración de Logging y Sentry se mantiene igual, está bien estructurada)
# Asegurarse que Sentry ignore errores de cancelación de tareas intencionales
if config('SENTRY_DSN', default=None):
    sentry_sdk.init(
        dsn=config('SENTRY_DSN'),
        integrations=[DjangoIntegration(), CeleryIntegration(), RedisIntegration()],
        traces_sample_rate=config('SENTRY_TRACES_SAMPLE_RATE', default=0.1, cast=float),
        send_default_pii=True,
        environment=config('ENVIRONMENT', default='production'),
    )

# Email configs... (Mantener igual)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@byteneko.com')

# Optimizaciones extra
MIDDLEWARE.insert(2, 'django.middleware.gzip.GZipMiddleware')