"""
Test settings for ByteNeko project.
Lightweight settings optimized for pytest.
"""

from .base import *  # noqa: F401,F403

# ============================================================
# CONFIGURACIÓN BÁSICA PARA TESTS
# ============================================================
DEBUG = False  # Simulamos entorno real pero sin HTTPS forzado
SECRET_KEY = 'test-secret-key-insecure-but-fast'

# Desactivamos explícitamente SSL por si acaso
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# ============================================================
# CACHE (Memoria RAM para velocidad extrema)
# ============================================================
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}

# ============================================================
# STATIC FILES STORAGE
# Use simple storage in tests to avoid requiring a collectstatic manifest.
# ============================================================
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# ============================================================
# BASE DE DATOS (SQLite en memoria)
# ============================================================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# ============================================================
# VELOCIDAD EXTRA (Hashing de contraseñas simple)
# ============================================================
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# ============================================================
# CELERY (Modo síncrono para tests)
# ============================================================
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = 'memory://'
CELERY_RESULT_BACKEND = 'cache+memory://'

# ============================================================
# LOGGING (Silencioso para no ensuciar la consola)
# ============================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'handlers': {
        'null': {
            'class': 'logging.NullHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['null'],
            'level': 'CRITICAL',
        },
        'core': {
            'handlers': ['null'],
            'level': 'CRITICAL',
        },
    },
}
