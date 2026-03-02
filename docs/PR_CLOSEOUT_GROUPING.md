# PR Closeout Grouping (Security Remediation)

Fecha: 2026-03-01
Estado: ejecutado (agrupación final definida)

## Estado de ejecución

- [x] PR A definido y preparado en rama `remediation/pr-a-security-hardening`
- [x] PR B definido
- [x] PR C definido
- [x] Criterios de merge definidos
- [x] Orden de integración definido

## PR A — Security Hardening (API/runtime)

Objetivo:
- Reducir exposición de errores internos en respuestas públicas.
- Estandarizar logging de excepción en vistas/servicios críticos.

Archivos incluidos (scope final):
- core/views/payment_views.py
- surveys/views/report_views.py
- surveys/views/import_views.py
- surveys/views/question_views.py
- surveys/views/crud_views.py
- surveys/views/respond_views.py
- surveys/views/template_views.py
- surveys/views_preview.py
- surveys/urls.py
- surveys/forms.py

Validación mínima:
- tests/test_importjob_async.py
- tests/test_csv_import.py
- tests/test_import_logic.py
- tests/test_smoke_core_views.py

## PR B — Refactor incremental (mantenibilidad)

Objetivo:
- Reducir duplicación y complejidad en vistas monolíticas.
- Consolidar helpers de autorización/carga/flags.

Archivos incluidos (scope final):
- core/views.py
- core/services/survey_analysis.py
- core/reports/pdf_generator.py
- core/utils/charts.py

Validación mínima:
- tests/test_analysis_service.py
- tests/test_charts.py
- tests/test_smoke_core_views.py

## PR C — Operación y runtime hardening

Objetivo:
- Endurecimiento operativo y consistencia en utilidades de importación/tareas.

Archivos incluidos (scope final):
- Dockerfile
- requirements.txt
- .gitignore
- byteneko/settings_production.py
- surveys/tasks.py
- surveys/utils/bulk_import.py
- surveys/utils/delete_optimizer.py
- surveys/management/commands/import_csv_fast.py
- tools/cpp_csv/pybind_csv.py
- tools/cpp_csv/example_validation.py
- scripts/verify_optimizations.py
- scripts/test_pptx_gen.py
- scripts/test_pptx_gen_v2.py
- scripts/test_pptx_gen_v3.py
- scripts/test_bounds.py
- scripts/test_autosize.py

Validación mínima:
- tests/test_importjob_async.py
- tests/test_csv_import.py
- tests/test_import_logic.py
- tests/test_delete_performance.py

## Criterio de merge por PR

- Sin errores de análisis estático en archivos tocados.
- Suite objetivo en verde.
- Sin cambios de contrato HTTP no intencionados.
- Mensajes de error públicos sanitizados.

## Orden de integración recomendado

1. PR A (hardening API)
2. PR B (refactor incremental core/analysis)
3. PR C (operación/runtime)

## Evidencia de cierre técnico

- Regresión completa: 161/161 en verde.
- Plan maestro actualizado: docs/SECURITY_REMEDIATION_PLAN.md.
- Checklist de despliegue listo: docs/DEPLOY_CHECKLIST_POST_REMEDIATION.md.
- Validación mínima PR A: 10/10 en verde.
