# Solución: Logs guardándose en archivos correspondientes

## Problema Identificado

Los archivos de logs (`app.log`, `error.log`, `performance.log`, `security.log`) no se estaban actualizando desde el 28 de noviembre, mientras que `server.log` sí se actualizaba. 

**Causa:** El archivo `byteneko/settings/local.py` tenía una configuración de LOGGING "minimalista" que sobrescribía la configuración completa definida en `byteneko/settings/base.py`, escribiendo solo en la consola y en `server.log`.

## Solución Implementada

Se corrigió la configuración de LOGGING en `byteneko/settings/local.py` para que mantenga todos los handlers y loggers necesarios:

### Archivos de logs y su propósito:

1. **app.log** (10 MB, 5 backups)
   - Logs generales de la aplicación
   - Recibe: django, core, surveys (nivel INFO+)

2. **error.log** (10 MB, 5 backups)
   - Solo errores (nivel ERROR)
   - Recibe: django.request, core, surveys

3. **server.log** (10 MB, 5 backups)
   - Logs del servidor y requests
   - Recibe: django, surveys

4. **performance.log** (10 MB, 3 backups)
   - Logs de rendimiento
   - Recibe: core.performance

5. **security.log** (5 MB, 10 backups)
   - Logs de seguridad
   - Recibe: django.security, core.security (nivel WARNING+)

### Loggers configurados:

```python
- django          → console, file_app, file_server
- django.request  → console, file_error
- django.security → console, file_security
- core            → console, file_app, file_error
- surveys         → console, file_app, file_error, file_server
- core.performance → console, file_performance
- core.security   → console, file_security
- root            → console, file_app
```

## Características:

- **RotatingFileHandler**: Los archivos rotan automáticamente cuando alcanzan el tamaño máximo
- **Formato verbose**: Incluye timestamp, nivel, módulo, función y número de línea
- **Backups**: Se mantienen múltiples versiones de cada archivo
- **Niveles apropiados**: DEBUG en desarrollo, INFO+ en producción

## Verificación:

Todos los archivos de logs están funcionando correctamente y se actualizaron el 2 de diciembre de 2025.

```
✓ OK     app.log                 101,773 bytes  2025-12-02 05:46:04
✓ OK     error.log               102,192 bytes  2025-12-02 05:46:04
✓ OK     server.log              340,674 bytes  2025-12-02 05:46:04
✓ OK     performance.log           1,565 bytes  2025-12-02 05:46:04
✓ OK     security.log                260 bytes  2025-12-02 05:46:04
```

## Scripts de utilidad creados:

- `test_logging.py`: Prueba que todos los loggers escriban en sus archivos correspondientes
- `verify_logs.py`: Verifica el estado de todos los archivos de logs

## Uso en código:

```python
import logging

# Logger general de la app
logger = logging.getLogger('core')
logger.info("Mensaje informativo")
logger.error("Mensaje de error")

# Logger de rendimiento
perf_logger = logging.getLogger('core.performance')
perf_logger.info("Operación completada en 0.5s")

# Logger de seguridad
sec_logger = logging.getLogger('core.security')
sec_logger.warning("Intento de acceso no autorizado")
```
