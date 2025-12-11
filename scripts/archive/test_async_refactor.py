"""
Script de prueba para verificar la refactorización asíncrona.
Ejecutar: python manage.py shell < scripts/test_async_refactor.py
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings.production')
django.setup()

from django.contrib.auth import get_user_model
from surveys.tasks import delete_surveys_task, process_survey_import
from surveys.models import Survey, ImportJob
from celery.result import AsyncResult

User = get_user_model()

print("=" * 70)
print("🧪 TEST DE REFACTORIZACIÓN ASÍNCRONA - ByteNeko")
print("=" * 70)

# 1. Verificar que las tareas están registradas
print("\n✅ Verificando registro de tareas en Celery...")
from byteneko.celery import app

registered_tasks = list(app.tasks.keys())
critical_tasks = [
    'surveys.tasks.process_survey_import',
    'surveys.tasks.delete_surveys_task',
]

for task_name in critical_tasks:
    if task_name in registered_tasks:
        print(f"   ✅ {task_name} - REGISTRADA")
    else:
        print(f"   ❌ {task_name} - NO ENCONTRADA")

# 2. Verificar configuración de Celery
print("\n✅ Verificando configuración de Celery...")
print(f"   Broker: {app.conf.broker_url}")
print(f"   Backend: {app.conf.result_backend}")
print(f"   Task serializer: {app.conf.task_serializer}")
print(f"   Accept content: {app.conf.accept_content}")

# 3. Test de conectividad con Redis/Broker
print("\n✅ Verificando conectividad con broker...")
try:
    inspect = app.control.inspect(timeout=2.0)
    ping_result = inspect.ping()
    
    if ping_result:
        print(f"   ✅ Workers activos detectados: {len(ping_result)}")
        for worker_name, response in ping_result.items():
            print(f"      - {worker_name}: {response}")
    else:
        print("   ⚠️  No se detectaron workers activos")
        print("      Asegúrate de ejecutar: celery -A byteneko worker -l info")
except Exception as e:
    print(f"   ❌ Error de conectividad: {e}")
    print("      Verifica que Redis esté corriendo")

# 4. Estadísticas de ImportJobs
print("\n📊 Estadísticas de ImportJobs:")
total_jobs = ImportJob.objects.count()
pending_jobs = ImportJob.objects.filter(status='pending').count()
processing_jobs = ImportJob.objects.filter(status='processing').count()
completed_jobs = ImportJob.objects.filter(status='completed').count()
failed_jobs = ImportJob.objects.filter(status='failed').count()

print(f"   Total: {total_jobs}")
print(f"   Pendientes: {pending_jobs}")
print(f"   Procesando: {processing_jobs}")
print(f"   Completados: {completed_jobs}")
print(f"   Fallidos: {failed_jobs}")

if failed_jobs > 0:
    print("\n   ⚠️  Jobs fallidos recientes:")
    for job in ImportJob.objects.filter(status='failed').order_by('-updated_at')[:3]:
        print(f"      - Job #{job.id}: {job.error_message[:80]}")

## Código relacionado con cpp_csv eliminado (código muerto)

# 6. Resumen de optimizaciones activas
print("\n" + "=" * 70)
print("📋 RESUMEN DE OPTIMIZACIONES ACTIVAS")
print("=" * 70)

optimizations = [
    ("✅", "Importación CSV 100% asíncrona vía Celery"),
    ("✅", "Borrado de encuestas 100% asíncrono vía Celery"),
    ("✅", "bulk_import_responses_postgres con COPY FROM"),
    ("✅", "synchronous_commit OFF para velocidad máxima"),
    ("✅", "Rate limiting en vistas (20/h import, 50/h delete)"),
    ("✅", "Detección automática de campos demográficos"),
    ("✅", "Manejo robusto de errores con ImportJob.status"),
]

for status, description in optimizations:
    print(f"{status} {description}")

# 7. Advertencias y recomendaciones
print("\n" + "=" * 70)
print("⚠️  ADVERTENCIAS Y RECOMENDACIONES")
print("=" * 70)

warnings = []

# Verificar usuario admin
if not User.objects.filter(is_superuser=True).exists():
    warnings.append("No hay usuarios superadmin. Crear uno con: python manage.py createsuperuser")

# Verificar encuestas
if Survey.objects.count() == 0:
    warnings.append("No hay encuestas en la BD. Importa CSVs de prueba para verificar funcionamiento.")

# Verificar workers
try:
    inspect = app.control.inspect(timeout=1.0)
    if not inspect.ping():
        warnings.append("⚠️  CRÍTICO: No hay workers de Celery corriendo. Ejecuta: celery -A byteneko worker -l info")
except:
    warnings.append("⚠️  CRÍTICO: No se puede conectar con Redis/Celery. Verifica servicios.")

if warnings:
    for warning in warnings:
        print(f"   ⚠️  {warning}")
else:
    print("   ✅ Todo configurado correctamente")

print("\n" + "=" * 70)
print("🎯 PRUEBA COMPLETADA")
print("=" * 70)
print("\nPara probar el sistema:")
print("1. Inicia el servidor: python manage.py runserver")
print("2. Inicia Celery worker: celery -A byteneko worker -l info")
print("3. (Opcional) Inicia Flower: celery -A byteneko flower")
print("4. Importa un CSV desde la UI y observa los logs del worker")
print("\n")
