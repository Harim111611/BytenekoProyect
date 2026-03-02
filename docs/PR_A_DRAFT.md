# PR A Draft — Security Hardening (API/runtime)

Branch: remediation/pr-a-security-hardening
Fecha: 2026-03-01

## Resumen

Este PR consolida hardening de seguridad en endpoints y vistas críticas:
- sanitización de errores públicos,
- estandarización de logging de excepciones,
- endurecimiento de flujo Stripe y endpoints de import/report,
- ajustes de rutas/validaciones para mantener contratos API estables.

## Scope

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

## Riesgos

- Bajo/medio: cambios de manejo de errores y respuestas 4xx/5xx.
- Mitigación: mensajes estables, trazas en servidor, suite de regresión enfocada.

## Validación ejecutada

- tests/test_importjob_async.py
- tests/test_csv_import.py
- tests/test_import_logic.py
- tests/test_smoke_core_views.py

Resultado: 10 passed, 0 failed.

## Checklist de merge

- [x] Sin errores de análisis estático en archivos tocados.
- [x] Suite objetivo en verde.
- [x] Sin cambios de contrato HTTP no intencionados.
- [x] Mensajes de error públicos sanitizados.
