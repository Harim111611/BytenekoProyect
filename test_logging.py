"""
Script de prueba para verificar que los logs se escriben correctamente en todos los archivos.
"""
import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings')
django.setup()

import logging

# Obtener los diferentes loggers
logger_django = logging.getLogger('django')
logger_core = logging.getLogger('core')
logger_surveys = logging.getLogger('surveys')
logger_performance = logging.getLogger('core.performance')
logger_security = logging.getLogger('core.security')

print("=" * 80)
print("PRUEBA DE LOGGING - Verificando escritura en archivos")
print("=" * 80)

# Test 1: Logger Django (debería ir a app.log y server.log)
print("\n1. Escribiendo en logger 'django'...")
logger_django.info("TEST: Mensaje INFO en logger django")
logger_django.warning("TEST: Mensaje WARNING en logger django")

# Test 2: Logger Core (debería ir a app.log y error.log para errores)
print("2. Escribiendo en logger 'core'...")
logger_core.debug("TEST: Mensaje DEBUG en logger core")
logger_core.info("TEST: Mensaje INFO en logger core")
logger_core.error("TEST: Mensaje ERROR en logger core")

# Test 3: Logger Surveys (debería ir a app.log, server.log y error.log para errores)
print("3. Escribiendo en logger 'surveys'...")
logger_surveys.info("TEST: Mensaje INFO en logger surveys")
logger_surveys.error("TEST: Mensaje ERROR en logger surveys")

# Test 4: Logger Performance (debería ir a performance.log)
print("4. Escribiendo en logger 'core.performance'...")
logger_performance.info("TEST: Mensaje de rendimiento - operación completada en 0.5s")

# Test 5: Logger Security (debería ir a security.log)
print("5. Escribiendo en logger 'core.security'...")
logger_security.warning("TEST: Mensaje de seguridad - intento de acceso sospechoso")

print("\n" + "=" * 80)
print("PRUEBA COMPLETADA")
print("=" * 80)
print("\nVerifica los siguientes archivos:")
print("- logs/app.log (debería tener mensajes de django, core, surveys)")
print("- logs/error.log (debería tener mensajes ERROR)")
print("- logs/server.log (debería tener mensajes de django y surveys)")
print("- logs/performance.log (debería tener mensajes de rendimiento)")
print("- logs/security.log (debería tener mensajes de seguridad)")
print("\n")
