# Docs Pruebas - Documentación de Pruebas y Testing

Este directorio contiene documentación relacionada con pruebas del proyecto.

## Contenido

- Documentos de test cases
- Resultados de pruebas
- Reportes de cobertura
- Guías de testing

## Archivos Típicos

- `test_plan.md`: Plan de testing
- `test_results.md`: Resultados de pruebas
- `coverage_report.md`: Reporte de cobertura
- `test_scenarios.md`: Escenarios de test

## Estructura Recomendada

```
Pruebas/
├── README.md (este archivo)
├── test_plan.md
├── test_results/
│   ├── unit_tests.md
│   ├── integration_tests.md
│   └── smoke_tests.md
├── coverage/
│   └── coverage_report.md
└── scenarios/
    ├── user_scenarios.md
    └── edge_cases.md
```

## Testing en el Proyecto

### Ubicación de Tests
Los tests están centralizados en `/tests/` en la raíz del proyecto.

### Ejecución
```bash
# Todos los tests
pytest

# Tests específicos
pytest tests/test_surveys.py

# Con cobertura
pytest --cov=core --cov=surveys
```

### Tipos de Tests
- **Unit Tests**: Componentes individuales
- **Integration Tests**: Interacción entre componentes
- **Smoke Tests**: Funcionalidad básica
- **Performance Tests**: Rendimiento

## Documentación de Casos

Cada documento debe incluir:
- Objetivo del test
- Precondiciones
- Pasos
- Resultado esperado
- Resultado actual (después de ejecutar)

## Cobertura

Meta de cobertura: **>80%**

Generar reporte:
```bash
pytest --cov --cov-report=html
# Ver en htmlcov/index.html
```

## Automatización

Los tests se ejecutan automáticamente en:
- Commits locales (pre-commit hooks)
- Pull requests (CI/CD)
- Deployments (pre-deployment checks)

## Referencias

- [Pytest Documentation](https://docs.pytest.org/)
- [Django Testing Guide](https://docs.djangoproject.com/en/stable/topics/testing/)
