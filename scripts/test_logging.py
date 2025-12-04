#!/usr/bin/env python
"""
Script de prueba para verificar que los nuevos logs se generan correctamente.
Uso: python scripts/test_logging.py
"""

import os
import django
import sys
from pathlib import Path

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings.local')
django.setup()

import logging
from django.contrib.auth.models import User
from surveys.models import Survey
from surveys.signals import invalidate_survey_cache

# Obtener loggers
logger = logging.getLogger('surveys')
django_logger = logging.getLogger('django.request')

print("\n" + "="*80)
print("🧪 PRUEBA DE LOGGING - ByteNeko")
print("="*80 + "\n")

# Test 1: Crear una encuesta de prueba
print("📝 Test 1: Creando encuesta de prueba...")
try:
    user, _ = User.objects.get_or_create(username='test_user')
    survey = Survey.objects.create(
        title="Survey de Prueba",
        author=user,
        description="Para probar logs",
        status='active'
    )
    print(f"✅ Encuesta creada: {survey.id}")
    print("   Revisa los logs en: logs/surveys.log\n")
except Exception as e:
    print(f"❌ Error: {e}\n")

# Test 2: Simular log manual
print("📝 Test 2: Generando logs de prueba...")
logger.info(f"📊 Encuesta {survey.id} (test manual) - Caché invalidada | Usuario: test_user")
logger.info(f"✅ Opción respuesta 1 (creada) - Encuesta {survey.id} - Caché actualizada")
logger.info(f"❓ Pregunta 1 (creada) en encuesta {survey.id} - Caché invalidada")
logger.info(f"📝 nueva respuesta en encuesta {survey.id} - Caché actualizada")
print("✅ Logs generados\n")

# Test 3: Verificar archivos de log
print("📝 Test 3: Verificando archivos de logs...")
logs_dir = Path('logs')
log_files = {
    'app.log': logs_dir / 'app.log',
    'surveys.log': logs_dir / 'surveys.log',
    'error.log': logs_dir / 'error.log',
}

for name, path in log_files.items():
    if path.exists():
        size = path.stat().st_size / 1024  # KB
        lines = len(path.read_text().split('\n'))
        print(f"   ✅ {name}: {size:.1f} KB ({lines} líneas)")
    else:
        print(f"   ⚠️  {name}: No existe")

print("\n" + "="*80)
print("🎯 PRÓXIMOS PASOS:")
print("="*80)
print("""
1. Abre PowerShell y ejecuta:
   .\scripts\manage_logs.ps1 view

2. Selecciona 'surveys.log' para ver los nuevos logs

3. Verifica que ves los logs con emojis y formato detallado

4. Limpia los datos de prueba (opcional):
   python manage.py shell
   >>> from surveys.models import Survey
   >>> Survey.objects.filter(title="Survey de Prueba").delete()
   >>> exit()

5. Para monitorear en tiempo real:
   Get-Content logs\surveys.log -Tail 30 -Wait
""")
print("="*80 + "\n")
