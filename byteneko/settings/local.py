from .base import *
from decouple import config

# ============================================================
# CONFIGURACIÓN LOCAL DE ALTO RENDIMIENTO
# ============================================================

DEBUG = True

LOCAL_LAN_IP = config('LAN_IP', default='172.16.0.2')

ALLOWED_HOSTS = ['localhost', '127.0.0.1', LOCAL_LAN_IP]

# ============================================================
# MIDDLEWARE (con logging de requests)
# ============================================================
MIDDLEWARE = [
    'core.middleware_logging.RequestLoggingMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Para servir estáticos con Gunicorn
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# 1. CONFIGURACIÓN PARA HTTP EN DESARROLLO (usando manage.py runserver)
# Deshabilitar HTTPS en desarrollo - runserver solo soporta HTTP
SESSION_COOKIE_SECURE = False 
CSRF_COOKIE_SECURE = False 
SECURE_SSL_REDIRECT = False  

# Evitar colisiones con cookies previas (p.ej. si antes corriste settings de producción en el mismo host)
SESSION_COOKIE_NAME = 'byteneko_session_local'
CSRF_COOKIE_NAME = 'byteneko_csrftoken_local'

# AUTORIZAR HTTP LOCAL (para runserver)
CSRF_TRUSTED_ORIGINS = [
    'http://127.0.0.1:8000',
    'http://localhost:8000',
    'http://127.0.0.1:8001',
    'http://localhost:8001',
    'http://127.0.0.1:8080',
    'http://localhost:8080',
    'http://127.0.0.1:8010',
    'http://localhost:8010',
    f'http://{LOCAL_LAN_IP}:8000',
    f'http://{LOCAL_LAN_IP}:8010', 
]

# 2. ARCHIVOS ESTÁTICOS CON WHITENOISE
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# 3. BASE DE DATOS OPTIMIZADA PARA 4GB RAM
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='byteneko_dev'),
        'USER': config('DB_USER', default='byteneko_user'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default='127.0.0.1'),
        'PORT': config('DB_PORT', default='5432'),
        'ATOMIC_REQUESTS': False,  # No atomic requests para mejor performance
        'AUTOCOMMIT': True,
        'CONN_MAX_AGE': 300,  # 5 minutos de persistent connections
        'CONN_HEALTH_CHECKS': True,  # Check health de connections
        'OPTIONS': {
            'client_encoding': 'UTF8',
            'connect_timeout': 10,
            'options': '-c statement_timeout=30000',  # 30s timeout
        },
        # Pool de conexiones limitado
        'POOL_OPTIONS': {
            'POOL_SIZE': 10,  # Máximo 10 conexiones por proceso
            'MAX_OVERFLOW': 5,
        },
    }
}

# 4. CONFIGURACIÓN DE PLANTILLAS
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True, 
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# 5. LOGGING COMPLETO (mantiene todos los archivos de logs)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name} {module}.{funcName}:{lineno} - {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '[{levelname}] {asctime} - {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file_app': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(BASE_DIR / 'logs' / 'app.log'),
            'maxBytes': 1024 * 1024 * 10,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'file_error': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(BASE_DIR / 'logs' / 'error.log'),
            'maxBytes': 1024 * 1024 * 10,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'file_security': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(BASE_DIR / 'logs' / 'security.log'),
            'maxBytes': 1024 * 1024 * 5,  # 5 MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'file_performance': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(BASE_DIR / 'logs' / 'performance.log'),
            'maxBytes': 1024 * 1024 * 10,  # 10 MB
            'backupCount': 3,
            'formatter': 'verbose',
        },
        'file_server': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(BASE_DIR / 'logs' / 'server.log'),
            'maxBytes': 1024 * 1024 * 10,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file_app', 'file_server'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'file_error'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console', 'file_security'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'fontTools': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'matplotlib': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'matplotlib.font_manager': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'core': {
            'handlers': ['console', 'file_app', 'file_error'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'surveys': {
            'handlers': ['console', 'file_app', 'file_error', 'file_server'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'core.performance': {
            'handlers': ['console', 'file_performance'],
            'level': 'INFO',
            'propagate': False,
        },
        'core.security': {
            'handlers': ['console', 'file_security'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console', 'file_app'],
        'level': 'INFO',
    },
}
# ============================================================
# OPTIMIZACIONES PARA 4GB RAM Y MÚLTIPLES IMPORTACIONES
# ============================================================

# Usar cpp_csv para importaciones (CRÍTICO para rendimiento)
SURVEY_IMPORT_USE_CPP = True
SURVEY_IMPORT_USE_COPY_QR = True

# Chunks más pequeños para evitar picos de memoria
SURVEY_IMPORT_CHUNK_SIZE = 2500  # Reducido de 5000 a 2500
SURVEY_IMPORT_SAMPLE_SIZE = 5000  # Reducido de 10000 a 5000
SURVEY_DELETE_CHUNK_SIZE = 2000  # Reducido de 5000 a 2000

# Límites de memoria para procesamiento
MAX_CSV_FILE_SIZE_MB = 50  # Máximo 50MB por archivo CSV
MAX_CONCURRENT_IMPORTS = 6  # Máximo 6 importaciones simultáneas

# ============================================================
# CELERY OPTIMIZADO PARA MÚLTIPLES USUARIOS
# ============================================================

# Configuraciones de worker optimizadas
CELERY_WORKER_PREFETCH_MULTIPLIER = 2  # Prefetch 2 tareas
CELERY_WORKER_MAX_TASKS_PER_CHILD = 100  # Reciclar después de 100 tareas
CELERY_TASK_TIME_LIMIT = 1800  # 30 min hard limit
CELERY_TASK_SOFT_TIME_LIMIT = 1500  # 25 min soft limit

# Configuraciones de cola
CELERY_TASK_ACKS_LATE = True  # Ack después de completar
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_DISABLE_RATE_LIMITS = True

# Compresión para ahorrar memoria
CELERY_TASK_COMPRESSION = 'gzip'
CELERY_RESULT_COMPRESSION = 'gzip'
CELERY_RESULT_EXPIRES = 3600  # 1 hora

# ============================================================
# CACHE OPTIMIZADO PARA 4GB RAM
# ============================================================

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
            'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 20,  # Limitado para 4GB
                'retry_on_timeout': True,
            },
            'IGNORE_EXCEPTIONS': True,  # No fallar si Redis cae
        },
        'KEY_PREFIX': 'byteneko',
        'TIMEOUT': 300,  # 5 minutos por defecto
    }
}

# Session en Redis para liberar DB
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# ============================================================
# OPTIMIZACIONES DE MEMORIA
# ============================================================

# Reducir DATA_UPLOAD_MAX_MEMORY_SIZE para controlar picos
# Permitir override por env (útil para docker-compose y pruebas con CSV grandes)
DATA_UPLOAD_MAX_MEMORY_SIZE = config('DATA_UPLOAD_MAX_MEMORY_SIZE', default=52428800, cast=int)  # 50MB
FILE_UPLOAD_MAX_MEMORY_SIZE = config('FILE_UPLOAD_MAX_MEMORY_SIZE', default=10485760, cast=int)  # 10MB
FILE_UPLOAD_HANDLERS = [
    'django.core.files.uploadhandler.TemporaryFileUploadHandler',  # Usar disco, no memoria
]

# Paginación por defecto más agresiva
REST_FRAMEWORK_DEFAULT_PAGE_SIZE = 25  # Reducido de 50

# Template caching - solo para producción, comentado en local
# TEMPLATES[0]['APP_DIRS'] = False
# TEMPLATES[0]['OPTIONS']['loaders'] = [
#     ('django.template.loaders.cached.Loader', [
#         'django.template.loaders.filesystem.Loader',
#         'django.template.loaders.app_directories.Loader',
#     ]),
# ]