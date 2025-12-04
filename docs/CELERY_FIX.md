# Solución al Problema de Importación Lenta con Celery

## Problema Identificado

Las importaciones de CSV (tanto single como multi import) estaban tardando "décadas" porque **las tareas de Celery no se estaban procesando**.

### Causa Raíz

El problema tenía múltiples capas:

1. **Routing de Colas Incorrecto**: Los decoradores `@shared_task` tenían parámetros `queue="imports"`, `queue="reports"`, `queue="charts"`, enviando las tareas a colas específicas.

2. **Worker No Escuchaba las Colas Correctas**: El worker de Celery se iniciaba con:
   ```bash
   celery -A byteneko worker --loglevel=info --pool=solo
   ```
   Esto significa que **solo escuchaba la cola por defecto** (`celery`), no las colas específicas (`imports`, `reports`, `charts`).

3. **Resultado**: Las tareas se enviaban a Redis en la cola `imports`, pero el worker nunca las consumía porque solo escuchaba en la cola `celery`.

## Solución Implementada

### 1. Eliminación de Parámetros `queue` en Decoradores

Se eliminaron los parámetros `queue` de todos los decoradores `@shared_task` en `surveys/tasks.py`:

**ANTES:**
```python
@shared_task(
    bind=True,
    name="surveys.tasks.process_survey_import",
    queue="imports",  # ❌ Enviaba a cola específica
    max_retries=1,
)
```

**DESPUÉS:**
```python
@shared_task(
    bind=True,
    name="surveys.tasks.process_survey_import",
    # ✅ Va a la cola por defecto que el worker escucha
    max_retries=1,
)
```

### 2. Actualización de `byteneko/celery.py`

Se comentaron las rutas de cola en la configuración de Celery para asegurar que todas las tareas vayan a la cola por defecto:

```python
# Queue routing - TODAS las tareas van a la cola por defecto
app.conf.task_routes = {
    # Por ahora comentadas para que todas vayan a la cola por defecto
    # 'surveys.tasks.generate_pdf_report': {'queue': 'reports'},
    # 'surveys.tasks.generate_pptx_report': {'queue': 'reports'},
    # 'surveys.tasks.generate_chart_*': {'queue': 'charts'},
    # 'surveys.tasks.process_survey_import': {'queue': 'imports'},
}
```

### 3. Actualización del Script de Inicio

Se actualizó `start/start_celery.ps1` para incluir `--concurrency=4`:

```powershell
celery -A byteneko worker --loglevel=info --pool=solo --concurrency=4
```

## Verificación

Después de los cambios:

```bash
python -c "from django import setup; import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings'); setup(); from surveys.tasks import process_survey_import; r = process_survey_import.delay(10); print(f'Task {r.id} sent!')"
```

**Resultado**:
- ✅ Task procesada correctamente
- ✅ Status: completed
- ✅ 10,000 filas procesadas
- ✅ Sin errores

## Opciones Futuras

Si en el futuro quieres usar colas específicas para organizar el trabajo:

### Opción A: Worker con Múltiples Colas

```bash
celery -A byteneko worker -Q celery,imports,reports,charts --loglevel=info
```

### Opción B: Múltiples Workers Especializados

```bash
# Worker para importaciones
celery -A byteneko worker -Q imports --loglevel=info -n worker_imports

# Worker para reportes
celery -A byteneko worker -Q reports --loglevel=info -n worker_reports
```

Luego reactivar los parámetros `queue` en los decoradores.

## Comandos Útiles de Diagnóstico

### Ver colas en Redis
```bash
redis-cli KEYS "*"
redis-cli LLEN celery
redis-cli LLEN imports
```

### Ver procesos de Celery
```powershell
Get-Process | Where-Object {$_.CommandLine -like "*celery*"}
```

### Limpiar Redis
```bash
redis-cli FLUSHALL
```

## Archivos Modificados

1. `surveys/tasks.py` - Eliminados parámetros `queue` de decoradores
2. `byteneko/celery.py` - Comentadas las rutas de cola
3. `start/start_celery.ps1` - Añadido `--concurrency=4`

## Impacto en Performance

Con Celery funcionando correctamente:
- ✅ Importaciones asíncronas procesadas en background
- ✅ UI responde inmediatamente
- ✅ Polling de status funciona correctamente
- ✅ cpp_csv se utiliza para máxima velocidad (si está disponible)
- ✅ Sin bloqueo del servidor Django

## Fecha de Corrección

4 de diciembre de 2025 - 01:08 AM
