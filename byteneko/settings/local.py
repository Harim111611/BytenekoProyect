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

# 2. OPTIMIZACIÓN DE ARCHIVOS ESTÁTICOS
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# 3. BASE DE DATOS OPTIMIZADA
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='byteneko_dev'),
        'USER': config('DB_USER', default='byteneko_user'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default='127.0.0.1'),
        'PORT': config('DB_PORT', default='5432'),
        'OPTIONS': {
            'client_encoding': 'UTF8',
        },
        'CONN_MAX_AGE': 600, 
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
            'level': 'ERROR',
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
# PARIDAD DE PRODUCCIÓN PARA IMPORTACIÓN
# ============================================================
SURVEY_IMPORT_USE_COPY_QR = True

# Tamaño del lote para inserción de datos (bulk_create / chunking de Pandas)
SURVEY_IMPORT_CHUNK_SIZE = 5000

# Tamaño de la muestra para detección de tipo de columna
SURVEY_IMPORT_SAMPLE_SIZE = 10000

# CRÍTICO: Tamaño del lote para eliminación masiva (chunked deletion)
SURVEY_DELETE_CHUNK_SIZE = 5000

# ============================================================
# CELERY (Modo asíncrono con worker real)
# ============================================================
# El broker URL se toma de base.py

# Configuraciones de Celery Development
CELERY_WORKER_PREFETCH_MULTIPLIER = 1 
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000 
CELERY_TASK_TIME_LIMIT = 300  # 5 min
CELERY_TASK_SOFT_TIME_LIMIT = 240 # 4 min