# Script para iniciar Redis (si no esta corriendo)
# Ejecutar: .\start_redis.ps1

Write-Host "Iniciando Redis..." -ForegroundColor Cyan

# Verificar si Redis ya esta corriendo
$redis = Get-Process redis-server -ErrorAction SilentlyContinue
if ($redis) {
    Write-Host "Redis ya esta corriendo (PID: $($redis.Id))" -ForegroundColor Yellow
} else {
    # Iniciar Redis en segundo plano
    Start-Process "C:\Program Files\Redis\redis-server.exe" -WindowStyle Hidden
    Start-Sleep -Seconds 2
    
    # Verificar que se inicio
    $redis = Get-Process redis-server -ErrorAction SilentlyContinue
    if ($redis) {
        Write-Host "Redis iniciado correctamente (PID: $($redis.Id))" -ForegroundColor Green
    } else {
        Write-Host "Error al iniciar Redis" -ForegroundColor Red
    }
}
