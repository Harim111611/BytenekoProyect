# Tests - Suite de Pruebas Automatizadas

Este directorio centraliza todos los tests del proyecto.

## Estructura

Los tests están organizados por funcionalidad:

- **test_cache_invalidation.py**: Tests de invalidación de caché
- **test_csv_contexts.py**: Tests de contextos CSV
- **test_csv_import.py**: Tests de importación CSV
- **test_delete_performance.py**: Tests de rendimiento de eliminaciones
- **test_helpers.py**: Tests de funciones auxiliares
- **test_hotel_csv.py**: Tests específicos de importación hotel
- **test_importjob_async.py**: Tests de tareas asincrónicas de importación
- **test_import_logic.py**: Tests de lógica de importación
- **test_import_speed.py**: Tests de velocidad de importación
- **test_mixins.py**: Tests de mixins reutilizables
- **test_refactoring.py**: Tests de refactorización
- **test_services.py**: Tests de servicios
- **test_smoke_core_views.py**: Smoke tests de vistas core
- **test_smoke_core_views_ratelimit.py**: Tests de rate limiting
- **test_smoke_logging_utils.py**: Tests de utilidades de logging
- **test_smoke_pptx_generator.py**: Tests de generador PowerPoint
- **test_smoke_surveys_models.py**: Tests de modelos de encuestas
- **test_smoke_views.py**: Smoke tests generales de vistas
- **test_surveys.py**: Tests de encuestas
- **test_survey_analysis.py**: Tests de análisis de encuestas
- **test_survey_models.py**: Tests de modelos de encuestas
- **test_validators.py**: Tests de validadores
- **test_views.py**: Tests de vistas

## Ejecución

### Todos los tests
```bash
pytest
```

### Tests específicos
```bash
pytest tests/test_surveys.py
```

### Con cobertura
```bash
pytest --cov=core --cov=surveys
```

### Generar reporte HTML
```bash
pytest --cov --cov-report=html
```

## Configuración

La configuración de pytest está en `conftest.py` (raíz del proyecto):
- Fixtures comunes
- Configuración de base de datos de test
- Autenticación de test
- Factories de datos de prueba

## Tipos de Tests

### Smoke Tests
Tests rápidos que verifican que la funcionalidad básica funcione:
- `test_smoke_*.py`

### Unit Tests
Tests de componentes individuales:
- `test_services.py`
- `test_helpers.py`
- `test_validators.py`

### Integration Tests
Tests que verifican integración entre componentes:
- `test_csv_import.py`
- `test_importjob_async.py`

### Performance Tests
Tests que miden rendimiento:
- `test_delete_performance.py`
- `test_import_speed.py`

## Cobertura

La cobertura se mide y reporta con `pytest-cov`:
- Objetivo: >80% de cobertura
- Reporte HTML en `htmlcov/` (después de generar)
- Archivo de configuración: `.coverage`

## Mejores Prácticas

1. **Nombre descriptivo**: Los tests deben describir qué prueban
2. **Un assert por test**: Facilita identificar el fallo
3. **Use fixtures**: Reutilize código de setup con `conftest.py`
4. **Arrange-Act-Assert**: Estructura clara del test
5. **Mock externo**: Mock llamadas a API, base de datos, etc.

## Debugging

```bash
# Modo verbose
pytest -v

# Modo debug con breakpoint
pytest --pdb

# Mostrar prints
pytest -s

# Tests que fallan últimamente
pytest --lf
```
