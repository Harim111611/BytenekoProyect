#!/usr/bin/env python
"""
Development HTTPS server using Werkzeug
"""
import os
import sys
import logging
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

# Asegurar que los logs se muestren en la consola
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(asctime)s %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout,
    force=True  # Forzar reconfiguración si ya estaba configurado
)

from werkzeug.serving import make_ssl_devcert
from werkzeug.serving import run_simple
from django.core.wsgi import get_wsgi_application

# Create SSL certificates if they don't exist
ssl_dir = BASE_DIR / 'ssl'
ssl_dir.mkdir(exist_ok=True)  # Asegurar que el directorio existe
cert_file = ssl_dir / 'cert.pem'
key_file = ssl_dir / 'key.pem'

if not cert_file.exists() or not key_file.exists():
    print("Creating SSL certificates...")
    try:
        # Crear certificado para localhost y 127.0.0.1
        make_ssl_devcert(str(cert_file), host='localhost')
        print(f"✅ Certificados creados: {cert_file}")
    except Exception as e:
        print(f"❌ Error creando certificados: {e}")
        print("Intentando crear certificados manualmente...")
        import subprocess
        # Intentar crear con OpenSSL si está disponible
        try:
            subprocess.run([
                'openssl', 'req', '-x509', '-newkey', 'rsa:4096', '-nodes',
                '-keyout', str(key_file), '-out', str(cert_file),
                '-days', '365', '-subj', '/CN=localhost'
            ], check=True)
            print(f"✅ Certificados creados con OpenSSL: {cert_file}")
        except:
            print("⚠️  No se pudieron crear los certificados automáticamente")
            raise

# Get Django WSGI application
application = get_wsgi_application()
application = StaticFilesHandler(application)

print("=" * 80)
print("Starting HTTPS development server on https://127.0.0.1:8000/")
print("SSL Certificate: {}".format(cert_file))
print("SSL Key: {}".format(key_file))
print(f"🔧 CONFIGURACIÓN ACTIVA: {os.environ['DJANGO_SETTINGS_MODULE']}")
print(f"🐞 MODO DEBUG: {settings.DEBUG}")
print("📋 Los logs de DELETE aparecerán aquí con el prefijo [DELETE]")
print("-" * 80)
print("⚠️  IMPORTANTE: Al acceder verás una advertencia de 'Página no segura'")
print("   Esto es NORMAL en desarrollo. Haz clic en 'Avanzado' → 'Continuar'")
print("=" * 80)
print("Press Ctrl+C to stop the server")
print()

# Run the server with increased timeout for long-running operations
# Increase socket timeout to handle long-running delete operations
import socket
socket.setdefaulttimeout(600)  # 10 minutes timeout for socket operations

# Usar puerto 8000 (el puerto estándar de Django)
# Si hay problemas, puedes cambiarlo a 8001, 8080, etc.
PORT = 8000

print("=" * 80)
print(f"Starting HTTPS development server on https://127.0.0.1:{PORT}/")
print("SSL Certificate: {}".format(cert_file))
print("SSL Key: {}".format(key_file))
print(f"🔧 CONFIGURACIÓN ACTIVA: {os.environ['DJANGO_SETTINGS_MODULE']}")
print(f"🐞 MODO DEBUG: {settings.DEBUG}")
print("📋 Los logs de DELETE aparecerán aquí con el prefijo [DELETE]")
print("-" * 80)
print("⚠️  IMPORTANTE: Al acceder verás una advertencia de 'Página no segura'")
print("   Esto es NORMAL en desarrollo. Haz clic en 'Avanzado' → 'Continuar'")
print("   O escribe 'thisisunsafe' en la página de error")
print("=" * 80)
print("Press Ctrl+C to stop the server")
print()

run_simple(
    '127.0.0.1',
    PORT,
    application,
    ssl_context=(str(cert_file), str(key_file)),
    use_reloader=True,
    use_debugger=True,
    threaded=True,
)