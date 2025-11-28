"""
Production settings for ByteNeko project.
Extends base settings with production-specific configurations.
"""

from .settings import *
from decouple import config, Csv
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.redis import RedisIntegration

# ============================================================
# SECURITY SETTINGS
# ============================================================

DEBUG = False

SECRET_KEY = config('SECRET_KEY')  # MUST be set in production

ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())

# HTTPS/SSL Settings
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# HSTS Settings
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Cookie Security
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Strict'
SESSION_COOKIE_AGE = 86400  # 24 hours

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Strict'

# Security Headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# ============================================================
# DATABASE CONFIGURATION - PostgreSQL
# ============================================================

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 600,  # Persistent connections (10 minutes)
        'CONN_HEALTH_CHECKS': True,  # Enable connection health checks (Django 4.1+)
        'OPTIONS': {
            'connect_timeout': 10,
            'options': '-c statement_timeout=30000',  # 30 seconds
            # Note: max_connections debe configurarse en postgresql.conf = 200
            # ALTER SYSTEM SET max_connections = 200;
            # ALTER SYSTEM SET shared_buffers = '2GB';  # 25% of RAM for high load
        },
        'ATOMIC_REQUESTS': True,  # Wrap each request in a transaction
    }
}

# ============================================================
# CACHE CONFIGURATION - Redis
# ============================================================

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 200,  # Increased from 50 to 200 for high concurrency
                'retry_on_timeout': True,
                'health_check_interval': 30,  # Check connection health every 30s
            },
            'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
        },
        'KEY_PREFIX': 'byteneko',
        'TIMEOUT': 300,  # 5 minutes default
    }
}

# Session cache
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# ============================================================
# CELERY CONFIGURATION
# ============================================================

CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://127.0.0.1:6379/0')

CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# Task settings
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 minutes
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 4
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000

# Result backend settings
CELERY_RESULT_EXTENDED = True
CELERY_RESULT_EXPIRES = 3600  # 1 hour

# Beat scheduler
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# ============================================================
# STATIC & MEDIA FILES
# ============================================================

STATIC_ROOT = BASE_DIR / 'staticfiles'
STATIC_URL = '/static/'

# WhiteNoise configuration
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files (AWS S3 - Optional)
if config('USE_S3', default=False, cast=bool):
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='us-east-1')
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
    }
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/'
else:
    MEDIA_ROOT = BASE_DIR / 'media'
    MEDIA_URL = '/media/'

# ============================================================
# LOGGING CONFIGURATION - Production
# ============================================================

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name} {module}.{funcName}:{lineno} - {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(name)s %(levelname)s %(message)s',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file_error': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'error.log',
            'maxBytes': 1024 * 1024 * 10,  # 10 MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'sentry': {
            'level': 'ERROR',
            'class': 'sentry_sdk.integrations.logging.EventHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file_error'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'file_error', 'sentry'],
            'level': 'ERROR',
            'propagate': False,
        },
        'core': {
            'handlers': ['console', 'file_error'],
            'level': 'INFO',
            'propagate': False,
        },
        'surveys': {
            'handlers': ['console', 'file_error'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console', 'file_error'],
            'level': 'INFO',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console', 'file_error'],
        'level': 'INFO',
    },
}

# ============================================================
# SENTRY CONFIGURATION
# ============================================================

if config('SENTRY_DSN', default=None):
    sentry_sdk.init(
        dsn=config('SENTRY_DSN'),
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        # Performance monitoring
        traces_sample_rate=config('SENTRY_TRACES_SAMPLE_RATE', default=0.1, cast=float),
        
        # Error sampling
        sample_rate=1.0,
        
        # Send user data
        send_default_pii=True,
        
        # Environment
        environment=config('ENVIRONMENT', default='production'),
        
        # Release tracking
        release=config('RELEASE_VERSION', default=None),
        
        # Before send hook to filter sensitive data
        before_send=lambda event, hint: event,
    )

# ============================================================
# EMAIL CONFIGURATION
# ============================================================

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@byteneko.com')

# Admin notifications
ADMINS = [
    (config('ADMIN_NAME', default='Admin'), config('ADMIN_EMAIL', default='admin@byteneko.com')),
]
MANAGERS = ADMINS

# ============================================================
# RATE LIMITING
# ============================================================

# Default rate limit settings
RATELIMIT_ENABLE = True
RATELIMIT_USE_CACHE = 'default'
RATELIMIT_VIEW = 'core.views_ratelimit.ratelimit_error'

# ============================================================
# PERFORMANCE OPTIMIZATIONS
# ============================================================

# Template caching
TEMPLATES[0]['APP_DIRS'] = False
TEMPLATES[0]['OPTIONS']['loaders'] = [
    ('django.template.loaders.cached.Loader', [
        'django.template.loaders.filesystem.Loader',
        'django.template.loaders.app_directories.Loader',
    ]),
]

# Disable browsable API in production (if using DRF)
# REST_FRAMEWORK = {
#     'DEFAULT_RENDERER_CLASSES': ('rest_framework.renderers.JSONRenderer',)
# }

# ============================================================
# ADDITIONAL SETTINGS
# ============================================================

# Disable debug toolbar in production
INSTALLED_APPS = [app for app in INSTALLED_APPS if 'debug_toolbar' not in app]

# Compress responses
MIDDLEWARE.insert(2, 'django.middleware.gzip.GZipMiddleware')

# Admin URL (for security, use custom URL)
ADMIN_URL = config('ADMIN_URL', default='admin/')
