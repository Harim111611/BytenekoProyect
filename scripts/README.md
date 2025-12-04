# Scripts - Utilidades y Scripts de Administración

Este directorio contiene scripts de utilidad para administración y mantenimiento del proyecto.

## Scripts Principales

- **check_surveys.py**: Verificar integridad de encuestas
- **create_test_survey.py**: Crear encuestas de prueba
- **export_data.py**: Exportar datos a formato externo
- **generate_test_csv.py**: Generar archivos CSV de prueba
- **inspect_analysis.py**: Inspeccionar datos de análisis
- **listar_encuestas.py**: Listar todas las encuestas del sistema
- **refactor_to_english.py**: Refactorización de nombres al inglés

## Comandos Personalizados

Los comandos de Django se encuentran en:
```
surveys/management/commands/
```

Ejecutar comando personalizado:
```bash
python manage.py nombre_comando
```

## Deployment

- **deploy.sh**: Script de deployment para producción

## Tools

El directorio `tools/` contiene:
- **check_analysis.py**: Verificar datos de análisis
- **cpp_csv/**: Módulo compilado para procesamiento CSV rápido

## Uso de Scripts

### Crear datos de prueba
```bash
python scripts/create_test_survey.py
python scripts/generate_test_csv.py
```

### Verificar integridad
```bash
python scripts/check_surveys.py
python scripts/inspect_analysis.py
```

### Exportar datos
```bash
python scripts/export_data.py
```

### Listar recursos
```bash
python scripts/listar_encuestas.py
```

## Tareas Automáticas

Para tareas periódicas, usar Celery Beat en `tasks.py`:

```python
from celery import shared_task

@shared_task
def mi_tarea():
    # Código a ejecutar
    pass
```

## Mejores Prácticas

1. **Documentación**: Cada script debe tener docstring
2. **Logging**: Usar logging para rastrear ejecución
3. **Error handling**: Manejar excepciones correctamente
4. **Idempotencia**: Los scripts deben ser seguros para ejecutar varias veces
5. **Reversibilidad**: Si es posible, permitir deshacer cambios
