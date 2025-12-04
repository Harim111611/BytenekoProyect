# Script para iniciar TODO el stack de desarrollo
# Ejecutar: .\start_all.ps1
# NOTA: Ejecuta Celery en una terminal separada de VS Code primero

Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "Iniciando ByteNeko - Django Server" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan

# 1. Verificar Redis
Write-Host "`n[1/3] Verificando Redis..." -ForegroundColor Yellow
$redis = Get-Process redis-server -ErrorAction SilentlyContinue
if (-not $redis) {
    Write-Host "      Iniciando Redis..." -ForegroundColor Yellow
    Start-Process "C:\Program Files\Redis\redis-server.exe" -WindowStyle Hidden
    Start-Sleep -Seconds 2
    Write-Host "      Redis corriendo" -ForegroundColor Green
} else {
    Write-Host "      Redis ya esta corriendo (PID: $($redis.Id))" -ForegroundColor Green
}

# 2. Recordatorio para Celery
Write-Host "`n[2/3] Celery Worker..." -ForegroundColor Yellow
Write-Host "      IMPORTANTE: Abre otra terminal en VS Code y ejecuta:" -ForegroundColor Cyan
Write-Host "      .\start_celery.ps1" -ForegroundColor White
Write-Host ""

# 3. Iniciar Django
Write-Host "[3/3] Iniciando Django Web Server..." -ForegroundColor Yellow
Start-Sleep -Seconds 1
Write-Host "`n=======================================" -ForegroundColor Cyan
Write-Host "Stack:" -ForegroundColor Green
Write-Host "  - Django: Iniciando en esta terminal..." -ForegroundColor White
Write-Host "  - Celery: Ejecuta en otra terminal" -ForegroundColor Yellow
Write-Host "  - Redis: Puerto 6379 (background)" -ForegroundColor White
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

& .\.venv\Scripts\activate.ps1
$env:DJANGO_SETTINGS_MODULE = "byteneko.settings"
python manage.py runserver 127.0.0.1:8010
