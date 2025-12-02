"""
Resumen de verificación de logs
Ejecutado: 2 de diciembre de 2025
"""

import os
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / 'logs'

print("=" * 80)
print("VERIFICACIÓN DE CONFIGURACIÓN DE LOGS")
print("=" * 80)

log_files = {
    'app.log': 'Logs generales de la aplicación (django, core, surveys)',
    'error.log': 'Logs de errores (ERROR level)',
    'server.log': 'Logs del servidor (django, surveys)',
    'performance.log': 'Logs de rendimiento (core.performance)',
    'security.log': 'Logs de seguridad (core.security)',
}

print("\nARCHIVOS DE LOGS:")
print("-" * 80)

all_ok = True
for filename, description in log_files.items():
    filepath = LOGS_DIR / filename
    if filepath.exists():
        size = filepath.stat().st_size
        mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
        status = "✓ OK" if size > 0 else "⚠ VACÍO"
        print(f"{status:8} {filename:20} {size:>10,} bytes  {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"         {description}")
        if size == 0:
            all_ok = False
    else:
        print(f"✗ ERROR  {filename:20} NO EXISTE")
        print(f"         {description}")
        all_ok = False
    print()

print("=" * 80)
if all_ok:
    print("✓ TODOS LOS ARCHIVOS DE LOGS ESTÁN FUNCIONANDO CORRECTAMENTE")
else:
    print("⚠ ALGUNOS ARCHIVOS REQUIEREN ATENCIÓN")
print("=" * 80)

print("\nCONFIGURACIÓN ACTUAL:")
print("-" * 80)
print("Archivo de configuración: byteneko/settings/local.py")
print("Loggers configurados:")
print("  - django          → console, file_app, file_server")
print("  - django.request  → console, file_error")
print("  - django.security → console, file_security")
print("  - core            → console, file_app, file_error")
print("  - surveys         → console, file_app, file_error, file_server")
print("  - core.performance → console, file_performance")
print("  - core.security   → console, file_security")
print("  - root            → console, file_app")
print()
