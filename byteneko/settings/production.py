from .base import *

# Production-specific settings
# For example: configure a different database, logging, etc.
# Ensure DEBUG is False in production
DEBUG = False

# Add your production domain(s) to ALLOWED_HOSTS
# ALLOWED_HOSTS = ['yourdomain.com', 'www.yourdomain.com']

# Configure static files for production
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
