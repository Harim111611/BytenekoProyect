#!/usr/bin/env python
"""
Development HTTPS server using Werkzeug
"""
import os
import sys
from django.contrib.staticfiles.handlers import StaticFilesHandler
from pathlib import Path
from django.conf import settings
# Add the project directory to the Python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Set Django settings
# Línea 15 (CORRECTO)
os.environ['DJANGO_SETTINGS_MODULE'] = 'byteneko.settings.local'
import django
django.setup()

from werkzeug.serving import make_ssl_devcert
from werkzeug.serving import run_simple
from django.core.wsgi import get_wsgi_application

# Create SSL certificates if they don't exist
ssl_dir = BASE_DIR / 'ssl'
cert_file = ssl_dir / 'cert.pem'
key_file = ssl_dir / 'key.pem'

if not cert_file.exists() or not key_file.exists():
    print("Creating SSL certificates...")
    make_ssl_devcert(str(cert_file), host='localhost')

# Get Django WSGI application
application = get_wsgi_application()
application = StaticFilesHandler(application)

print("Starting HTTPS development server on https://localhost:8000/")
print("SSL Certificate: {}".format(cert_file))
print("SSL Key: {}".format(key_file))
print(f"🔧 CONFIGURACIÓN ACTIVA: {os.environ['DJANGO_SETTINGS_MODULE']}")
print(f"🐞 MODO DEBUG: {settings.DEBUG}")
print("Press Ctrl+C to stop the server")

# Run the server
run_simple(
    'localhost',
    8000,
    application,
    ssl_context=(str(cert_file), str(key_file)),
    use_reloader=True,
    use_debugger=True,
)