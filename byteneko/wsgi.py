"""
WSGI config for byteneko project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Default to production; settings are dynamically selected by `byteneko.settings`
os.environ.setdefault('DJANGO_ENV', os.environ.get('DJANGO_ENV', 'production'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings')

application = get_wsgi_application()
