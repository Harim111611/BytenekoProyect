# Script para iniciar Celery Worker
# Ejecutar: .\start_celery.ps1

Write-Host "Iniciando Celery Worker..." -ForegroundColor Cyan

# Activar entorno virtual
& .\.venv\Scripts\activate.ps1

# Configurar settings
$env:DJANGO_SETTINGS_MODULE = "byteneko.settings"

# Iniciar Celery con 4 workers
Write-Host "Celery worker corriendo con 4 workers (pool=solo para Windows)" -ForegroundColor Green
Write-Host "Tareas disponibles: import, reports, cleanup" -ForegroundColor Yellow
Write-Host "Escuchando en TODAS las colas (default + imports + reports + charts)" -ForegroundColor Cyan
celery -A byteneko worker --loglevel=info --pool=solo --concurrency=4
