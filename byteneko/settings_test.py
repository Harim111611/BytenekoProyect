"""
Test settings for ByteNeko project.
Extends production settings but uses LocMemCache for testing.
"""

from .settings_production import *

# ============================================================
# CACHE CONFIGURATION - LocMemCache for testing
# ============================================================

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}

# ============================================================
# DATABASE CONFIGURATION - Use local settings for testing
# ============================================================

# Override database to use SQLite for testing (faster and more reliable)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',  # Use in-memory database for tests
    }
}

# ============================================================
# CELERY CONFIGURATION - Disabled for testing
# ============================================================

# Disable Celery for testing
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Override broker and result backend to avoid Redis dependency
CELERY_BROKER_URL = 'memory://'
CELERY_RESULT_BACKEND = 'cache+memory://'

# ============================================================
# SESSION CONFIGURATION - Use signed cookies for testing
# ============================================================

# Use signed cookies instead of cache to avoid Redis dependency
SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'

# ============================================================
# LOGGING - Simplified for testing
# ============================================================

LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
        },
    },
}