"""
Django settings for byteneko project.
Refactored by Senior Django Developer.
"""

from pathlib import Path
from decouple import config, Csv
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())
PUBLIC_BASE_URL = config('PUBLIC_BASE_URL', default='')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',  # <--- AGREGADO: Necesario para filtros como 'intcomma'

    # --- Mis Apps ---
    'core.apps.CoreConfig',
    'surveys.apps.SurveysConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'byteneko.urls'

APPEND_SLASH = True

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

WSGI_APPLICATION = 'byteneko.wsgi.application'


# Database
DATABASES = {
    'default': {
        'ENGINE': config('DB_ENGINE', default='django.db.backends.postgresql'),
        'NAME': config('DB_NAME', default='byteneko_db'),
        'USER': config('DB_USER', default='postgres'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default='127.0.0.1'),
        'PORT': config('DB_PORT', default='5433'),
        'ATOMIC_REQUESTS': False,  # Disable to allow async views
    }
}


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]


# Internationalization
from django.utils.translation import gettext_lazy as _

LANGUAGE_CODE = 'en-us'
LANGUAGES = [
    ('en', _('English')),
    ('es', _('Spanish')),
]
LOCALE_PATHS = [ BASE_DIR / 'locale', ]
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [ BASE_DIR / 'static', ]
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media Files (Uploads - CRÍTICO para ImportJobs)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_REDIRECT_URL = 'dashboard'
LOGIN_URL = 'login'
LOGOUT_REDIRECT_URL = 'login'


# ============================================================
# FILE UPLOAD LIMITS (Production Security)
# ============================================================
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50 MB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000

# ============================================================
# LOGGING CONFIGURATION
# ============================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': { 'format': '[{levelname}] {asctime} {name} {module}.{funcName}:{lineno} - {message}', 'style': '{', 'datefmt': '%Y-%m-%d %H:%M:%S', },
        'simple': { 'format': '[{levelname}] {asctime} - {message}', 'style': '{', 'datefmt': '%Y-%m-%d %H:%M:%S', },
        'detailed': { 'format': '{asctime} | {name:30} | {levelname:8} | {funcName:20} | {message}', 'style': '{', 'datefmt': '%Y-%m-%d %H:%M:%S', },
    },
    'filters': {
        'require_debug_false': { '()': 'django.utils.log.RequireDebugFalse', },
        'require_debug_true': { '()': 'django.utils.log.RequireDebugTrue', },
    },
    'handlers': {
        'console': { 'level': 'DEBUG' if DEBUG else 'INFO', 'class': 'logging.StreamHandler', 'formatter': 'detailed', },
        'file_app': { 'level': 'INFO', 'class': 'logging.handlers.RotatingFileHandler', 'filename': BASE_DIR / 'logs' / 'app.log', 'maxBytes': 1024 * 1024 * 10, 'backupCount': 5, 'formatter': 'detailed', },
        'file_error': { 'level': 'ERROR', 'class': 'logging.handlers.RotatingFileHandler', 'filename': BASE_DIR / 'logs' / 'error.log', 'maxBytes': 1024 * 1024 * 10, 'backupCount': 5, 'formatter': 'verbose', },
        'file_security': { 'level': 'WARNING', 'class': 'logging.handlers.RotatingFileHandler', 'filename': BASE_DIR / 'logs' / 'security.log', 'maxBytes': 1024 * 1024 * 5, 'backupCount': 10, 'formatter': 'verbose', },
        'file_surveys': { 'level': 'INFO', 'class': 'logging.handlers.RotatingFileHandler', 'filename': BASE_DIR / 'logs' / 'surveys.log', 'maxBytes': 1024 * 1024 * 10, 'backupCount': 5, 'formatter': 'detailed', },
        'mail_admins': { 'level': 'ERROR', 'class': 'django.utils.log.AdminEmailHandler', 'filters': ['require_debug_false'], 'formatter': 'verbose', },
    },
    'loggers': {
        'django': { 'handlers': ['console', 'file_app'], 'level': 'INFO', 'propagate': False, },
        'django.request': { 'handlers': ['console', 'file_error', 'mail_admins'], 'level': 'ERROR', 'propagate': False, },
        'django.security': { 'handlers': ['console', 'file_security'], 'level': 'WARNING', 'propagate': False, },
        'core': { 'handlers': ['console', 'file_app', 'file_error'], 'level': 'DEBUG' if DEBUG else 'INFO', 'propagate': False, },
        'surveys': { 'handlers': ['console', 'file_surveys', 'file_error'], 'level': 'DEBUG' if DEBUG else 'INFO', 'propagate': False, },
    },
    'root': { 'handlers': ['console', 'file_app'], 'level': 'INFO', },
}

# Ensure logs dir exists
logs_dir = BASE_DIR / 'logs'
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

# ============================================================
# CELERY CONFIGURATION
# ============================================================
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')
CELERY_WORKER_CONCURRENCY = config('CELERY_WORKER_CONCURRENCY', default=4, cast=int)
CELERY_WORKER_PREFETCH_MULTIPLIER = 4
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TIMEZONE = TIME_ZONE
CELERY_RESULT_EXPIRES = 3600
CELERY_RESULT_PERSISTENT = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_POOL_LIMIT = 10