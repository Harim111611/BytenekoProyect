# PR C Draft — Runtime/Operations Hardening

Branch sugerida: remediation/pr-c-runtime-ops
Fecha: 2026-03-01

## Resumen

Hardening operativo de contenedor, utilidades de importación y tareas async,
con foco en resiliencia, logging y seguridad de runtime.

## Scope

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

## Validación mínima sugerida

- tests/test_importjob_async.py
- tests/test_csv_import.py
- tests/test_import_logic.py
- tests/test_delete_performance.py
