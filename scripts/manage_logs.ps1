# Script para gestionar logs de ByteNeko
# Uso: .\scripts\manage_logs.ps1 [comando]

param(
    [string]$command = "help"
)

$logsDir = "logs"
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$archiveDir = "logs\archive\$timestamp"

function Show-Help {
    Write-Host @"
╔════════════════════════════════════════════════════════════════╗
║         Gestor de Logs - ByteNeko Survey System               ║
╚════════════════════════════════════════════════════════════════╝

COMANDOS DISPONIBLES:

  view        - Ver últimas líneas de logs (interactivo)
  clean       - Limpiar archivos de backup rotados
  archive     - Archivar logs actuales en carpeta timestamped
  stats       - Mostrar estadísticas de logs
  tail        - Monitorear logs en tiempo real
  help        - Mostrar esta ayuda

EJEMPLOS:

  .\scripts\manage_logs.ps1 view          # Ver logs
  .\scripts\manage_logs.ps1 clean         # Limpiar backups
  .\scripts\manage_logs.ps1 archive       # Archivar
  .\scripts\manage_logs.ps1 tail app.log  # Monitorear app.log
  .\scripts\manage_logs.ps1 stats         # Estadísticas

"@
}

function View-Logs {
    Write-Host "`n📋 Selecciona un archivo para ver:" -ForegroundColor Cyan
    $files = Get-ChildItem $logsDir -Filter "*.log" -ErrorAction SilentlyContinue | 
        Where-Object { $_.PSIsContainer -eq $false }
    
    $i = 1
    $files | ForEach-Object {
        $size = [math]::Round($_.Length / 1KB, 2)
        Write-Host "$i) $($_.Name) ($size KB)" -ForegroundColor Yellow
        $i++
    }
    
    $selection = Read-Host "`nSelecciona número (1-$($files.Count))"
    
    if ($selection -gt 0 -and $selection -le $files.Count) {
        $selectedFile = $files[$selection - 1]
        $lines = Read-Host "Líneas a mostrar (defecto: 50)"
        if ($lines -eq "") { $lines = 50 }
        
        Write-Host "`n📄 Últimas $lines líneas de $($selectedFile.Name):`n" -ForegroundColor Green
        Get-Content "$logsDir\$($selectedFile.Name)" -Tail $lines | ForEach-Object {
            # Colorear según tipo de línea
            if ($_ -match "❌|ERROR|CRITICAL") {
                Write-Host $_ -ForegroundColor Red
            } elseif ($_ -match "⚠️|WARNING") {
                Write-Host $_ -ForegroundColor Yellow
            } elseif ($_ -match "✅|INFO") {
                Write-Host $_ -ForegroundColor Green
            } elseif ($_ -match "📊|📝|📋|❓|✅") {
                Write-Host $_ -ForegroundColor Cyan
            } else {
                Write-Host $_
            }
        }
    } else {
        Write-Host "❌ Selección inválida" -ForegroundColor Red
    }
}

function Clean-Logs {
    Write-Host "`n🧹 Limpiando archivos de backup rotados..." -ForegroundColor Yellow
    
    $backups = Get-ChildItem $logsDir -Filter "*.log.*" -ErrorAction SilentlyContinue
    
    if ($backups.Count -eq 0) {
        Write-Host "✅ No hay archivos de backup para limpiar" -ForegroundColor Green
    } else {
        Write-Host "Encontrados $($backups.Count) archivos de backup:"
        $backups | ForEach-Object {
            $size = [math]::Round($_.Length / 1KB, 2)
            Write-Host "  - $($_.Name) ($size KB)" -ForegroundColor Gray
        }
        
        $confirm = Read-Host "`n¿Eliminar estos archivos? (s/n)"
        
        if ($confirm -eq "s" -or $confirm -eq "S") {
            $backups | Remove-Item -Force
            Write-Host "✅ Archivos de backup eliminados" -ForegroundColor Green
        } else {
            Write-Host "❌ Operación cancelada" -ForegroundColor Yellow
        }
    }
}

function Archive-Logs {
    Write-Host "`n📦 Archivando logs actuales..." -ForegroundColor Yellow
    
    # Crear directorio de archivo
    if (!(Test-Path $archiveDir)) {
        New-Item -ItemType Directory -Path $archiveDir -Force | Out-Null
    }
    
    $logs = Get-ChildItem $logsDir -Filter "*.log" -ErrorAction SilentlyContinue | 
        Where-Object { $_.PSIsContainer -eq $false }
    
    if ($logs.Count -eq 0) {
        Write-Host "❌ No hay logs para archivar" -ForegroundColor Red
        return
    }
    
    Write-Host "Archivando $($logs.Count) archivos..." -ForegroundColor Cyan
    
    $logs | ForEach-Object {
        $size = [math]::Round($_.Length / 1MB, 2)
        Copy-Item "$logsDir\$($_.Name)" "$archiveDir\$($_.Name)"
        Write-Host "  ✓ $($_.Name) ($size MB)" -ForegroundColor Green
    }
    
    Write-Host "`n✅ Logs archivados en: $archiveDir" -ForegroundColor Green
}

function Show-Stats {
    Write-Host "`n📊 Estadísticas de Logs" -ForegroundColor Cyan
    Write-Host "═" * 50
    
    $logs = Get-ChildItem $logsDir -Filter "*.log" -ErrorAction SilentlyContinue | 
        Where-Object { $_.PSIsContainer -eq $false }
    
    if ($logs.Count -eq 0) {
        Write-Host "❌ No hay logs" -ForegroundColor Red
        return
    }
    
    $totalSize = 0
    Write-Host "`nArchivos principales:" -ForegroundColor Yellow
    $logs | Sort-Object Length -Descending | ForEach-Object {
        $size = [math]::Round($_.Length / 1MB, 2)
        $totalSize += $_.Length
        $lines = @(Get-Content "$logsDir\$($_.Name)").Count
        Write-Host "  $($_.Name)" -ForegroundColor Green
        Write-Host "    Tamaño: $size MB | Líneas: $lines" -ForegroundColor Gray
    }
    
    $backups = Get-ChildItem $logsDir -Filter "*.log.*" -ErrorAction SilentlyContinue
    if ($backups.Count -gt 0) {
        $backupSize = ($backups | Measure-Object -Property Length -Sum).Sum
        $backupSize = [math]::Round($backupSize / 1MB, 2)
        Write-Host "`nArchivos de backup: $($backups.Count)" -ForegroundColor Yellow
        Write-Host "  Tamaño total: $backupSize MB" -ForegroundColor Gray
        $totalSize += $backupSize * 1MB
    }
    
    $totalSize = [math]::Round($totalSize / 1MB, 2)
    Write-Host "`n📌 Tamaño Total: $totalSize MB" -ForegroundColor Cyan
    Write-Host "═" * 50
}

function Tail-Logs {
    param(
        [string]$logFile = "app.log"
    )
    
    $logPath = "$logsDir\$logFile"
    
    if (!(Test-Path $logPath)) {
        Write-Host "❌ Archivo no encontrado: $logPath" -ForegroundColor Red
        return
    }
    
    Write-Host "`n👁️  Monitoreando $logFile (Presiona Ctrl+C para salir)...`n" -ForegroundColor Cyan
    
    Get-Content $logPath -Tail 20 -Wait | ForEach-Object {
        # Colorear según tipo
        if ($_ -match "❌|ERROR|CRITICAL") {
            Write-Host $_ -ForegroundColor Red
        } elseif ($_ -match "⚠️|WARNING") {
            Write-Host $_ -ForegroundColor Yellow
        } elseif ($_ -match "✅|INFO") {
            Write-Host $_ -ForegroundColor Green
        } elseif ($_ -match "📊|📝|📋|❓") {
            Write-Host $_ -ForegroundColor Cyan
        } else {
            Write-Host $_
        }
    }
}

# Ejecutar comando
switch ($command.ToLower()) {
    "view" { View-Logs }
    "clean" { Clean-Logs }
    "archive" { Archive-Logs }
    "stats" { Show-Stats }
    "tail" { 
        if ($args.Count -gt 0) {
            Tail-Logs $args[0]
        } else {
            Write-Host "Monitoreando app.log (usa: tail [archivo] para otros)"
            Tail-Logs "app.log"
        }
    }
    default { Show-Help }
}
