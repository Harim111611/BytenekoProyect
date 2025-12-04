# Script para iniciar Django Web Server
# Ejecutar: .\start_django.ps1

Write-Host "Iniciando Django Web Server..." -ForegroundColor Cyan

# Limpiar variable de entorno
Remove-Item Env:DJANGO_SETTINGS_MODULE -ErrorAction SilentlyContinue

# Activar entorno virtual
& .\.venv\Scripts\activate.ps1

# Configurar settings
$env:DJANGO_SETTINGS_MODULE = "byteneko.settings"

# Iniciar servidor
Write-Host "Django corriendo en http://127.0.0.1:8010" -ForegroundColor Green
python manage.py runserver 127.0.0.1:8010
