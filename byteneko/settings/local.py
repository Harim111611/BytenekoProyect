from .base import *
from decouple import config

# ============================================================
# CONFIGURACIÓN LOCAL DE ALTO RENDIMIENTO
# ============================================================

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# 1. CONFIGURACIÓN PARA HTTP EN DESARROLLO (usando manage.py runserver)
# Deshabilitar HTTPS en desarrollo - runserver solo soporta HTTP
SESSION_COOKIE_SECURE = False  # Permitir cookies en HTTP
CSRF_COOKIE_SECURE = False  # Permitir CSRF en HTTP
SECURE_SSL_REDIRECT = False  # No forzar redirección a HTTPS

# AUTORIZAR HTTP LOCAL (para runserver)
# Incluimos múltiples puertos por si hay problemas con HSTS
CSRF_TRUSTED_ORIGINS = [
    'http://127.0.0.1:8000',  # HTTP puerto 8000
    'http://localhost:8000',
    'http://127.0.0.1:8001',  # HTTP puerto 8001 (alternativo)
    'http://localhost:8001',
    'http://127.0.0.1:8080',  # HTTP puerto 8080 (alternativo)
    'http://localhost:8080',
]

# 2. OPTIMIZACIÓN DE ARCHIVOS ESTÁTICOS
# En local usamos el almacenamiento simple para evitar errores de "Manifest missing"
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
        # Mantiene la conexión viva para eliminar el lag de 500ms por query
        'CONN_MAX_AGE': 600, 
    }
}

# 4. CACHÉ DE PLANTILLAS (CORREGIDO)
# Esto hace que navegar por el menú sea instantáneo.
# NOTA: Si cambias un HTML, tendrás que reiniciar el servidor para ver el cambio.
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': False,  # ⚠️ IMPORTANTE: Debe ser False cuando usamos 'loaders'
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
            'loaders': [
                ('django.template.loaders.cached.Loader', [
                    'django.template.loaders.filesystem.Loader',
                    'django.template.loaders.app_directories.Loader',
                ]),
            ],
        },
    },
]

# 5. LOGGING MINIMALISTA (Elimina lag de disco)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': str(BASE_DIR / "logs" / "server.log"),
            'mode': 'a',
            'encoding': 'utf-8',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'surveys': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    }
}
# ... aquí van tus otras configuraciones de local.py ...
# por ejemplo: DATABASES, LOGGING, etc.

# ============================================================
# CELERY (Modo síncrono para desarrollo)
# ============================================================
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = 'memory://'
CELERY_RESULT_BACKEND = 'cache+memory://'
