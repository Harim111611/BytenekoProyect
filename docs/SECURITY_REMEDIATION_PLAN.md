# Security & Code Smell Remediation Plan (Byteneko)

Fecha: 2026-03-01
Alcance: hardening de seguridad + reducción de code smells en backend Django.

## Estado actual

- ✅ Sprint A (P0) implementado.
- ✅ CVEs en dependencias directas corregidas (auditoría limpia).
- ✅ Endpoints críticos con menor exposición de errores internos.
- ✅ Rate limiting aplicado en importación/preview.
- ✅ Inicio de Sprint B (P1): webhook Stripe con idempotencia básica y ruta duplicada corregida.
- ✅ Hardening extra en Stripe: webhook solo POST + tolerancia de firma configurable.
- ✅ Smoke tests de core views en verde tras cambios.
- ✅ Regresión focalizada (importación + vistas críticas) en verde.
- ✅ Refactor incremental en importación: helpers comunes de auth/método y menor duplicación en vistas async.
- ✅ Tests de importación tras refactor en verde (8/8).
- ✅ Refactor incremental en reportes: helpers de autenticación/autorización reutilizables en vistas async.
- ✅ Tests de vistas y smoke tras refactor en verde (11/11).
- ✅ Refactor incremental en core/views: helper reutilizable para resolver encuesta por id/public_id del propietario.
- ✅ Sanitización adicional en errores de preview/PDF para evitar fuga de detalles internos.
- ✅ Validación posterior al refactor en verde (4/4 tests de core/views).
- ✅ Refactor adicional en core/views: helper para parsear flags de reportes y selector unificado de identificador de encuesta.
- ✅ Refactor adicional en report_views: reutilización de helper de autorización en endpoints de estado/segmentos.
- ✅ Validación de regresión de vistas tras refactor en verde (9/9).
- ✅ Manejo de excepciones en core/views mejorado (`logger.exception`) sin exponer detalles al cliente.
- ✅ Smoke de core/views posterior al ajuste en verde (2/2).
- ✅ Capturas de excepciones de BD tipadas en dashboard de analytics (`DatabaseError`) con logging explícito.
- ✅ Estandarización de logging de excepciones en report_views (`logger.exception`).
- ✅ Smoke/regresión posterior en verde (9/9).
- ✅ Sanitización adicional de errores internos en `question_views` y `crud_views` (sin `str(e)` en respuestas API).
- ✅ Regresión de vistas posterior a sanitización en verde (11/11).
- ✅ Logging de excepciones en pagos estandarizado (`logger.exception` con trazas completas).
- ✅ Hardening de contenedor aplicado: ejecución como usuario no-root en [Dockerfile](../Dockerfile).
- ✅ Smoke test de core tras cambios en verde (2/2).
- ✅ Sanitización adicional en generación de crosstab: error público genérico + trazas internas en logs.
- ✅ Estandarización de logging de excepciones en endpoints de análisis/reportes async.
- ✅ Regresión focalizada de análisis/charts en verde (12/12).
- ✅ Estandarización de respuestas 403 en `report_views` (sin eco de mensajes de excepción).
- ✅ Smoke tests posteriores en verde (3/3).
- ✅ Estandarización adicional de logging de excepciones en `report_views` (sin f-strings de error, con contexto estructurado).
- ✅ Hardening de logging en `template_views` y `views_preview` (sin interpolar excepción en mensaje).
- ✅ Validación de regresión posterior en verde (10/10).
- ✅ Hardening adicional en `core/views/payment_views.py`: eliminación de excepciones no usadas y logging con contexto.
- ✅ Estandarización de manejo de excepciones en `core/views.py` para preview/PDF/PPTX (sin interpolación de error).
- ✅ Regresión posterior de core en verde (10/10).
- ✅ Ajuste de `ValidationError` en cambio de estado (`report_views`) para mensaje controlado y consistente.
- ✅ Smoke test ratelimit/core posterior en verde (1/1).
- ✅ Hardening en `respond_views`: excepción final con `logger.exception` y contexto estructurado.
- ✅ Hardening en `crud_views`: eliminación de f-strings con excepción y logging consistente en creación/borrado masivo/estado de tareas.
- ✅ Hardening en `question_views`: logging parametrizado y excepciones estandarizadas (`logger.exception`).
- ✅ Validación posterior de importación en verde (2/2).
- ✅ Hardening en `core/utils/charts.py`: manejo de fallos Plotly/heatmap con `logger.exception` consistente.
- ✅ Hardening en `core/reports/pdf_generator.py`: errores críticos/globales sin interpolación de excepción y con contexto.
- ✅ Ajuste en `TimelineEngine` para logging de excepción consistente.
- ✅ Regresión posterior de charts/análisis/narrativa en verde (12/12).
- ✅ Hardening en `surveys/utils/delete_optimizer.py`: sanitización de error de salida y logging parametrizado.
- ✅ Hardening en `surveys/management/commands/import_csv_fast.py`: error controlado por consola + logging interno con contexto.
- ✅ Ajuste en `surveys/forms.py` para evitar fallback con `str(e)` en validación de estado.
- ✅ Ajuste en `SurveyDeleteView` (`crud_views`) para logging consistente en fallback de Celery.
- ✅ Regresión posterior de import/delete en verde (4/4).
- ✅ Hardening en `surveys/utils/bulk_import.py`: logging parametrizado/`logger.exception` en lectura CSV/COPY y progreso.
- ✅ Hardening en `surveys/tasks.py`: logging consistente en tareas Celery de importación/borrado y fallback de cleanup.
- ✅ Regresión posterior de importación async/lógica en verde (8/8).
- ✅ Hardening en `tools/cpp_csv/pybind_csv.py`: wrappers con `logger.exception` y sin interpolación manual de excepciones.
- ✅ Limpieza menor en `tools/cpp_csv/example_validation.py` para captura genérica segura en script de ejemplo.
- ✅ Regresión posterior de importación en verde (7/7).
- ✅ Hardening adicional en `surveys/views/import_views.py`: estandarización de `logger.exception` en preview/start/status/import-existing async.
- ✅ Regresión posterior de importación async/lógica en verde (8/8).
- ✅ Limpieza residual en scripts auxiliares (`scripts/test_pptx_gen*.py`, `scripts/test_bounds.py`, `scripts/test_autosize.py`, `scripts/verify_optimizations.py`) para manejo consistente de excepciones.
- ✅ Verificación de core/import tras limpieza de scripts en verde (8/8).
- ✅ Barrida final de remanentes `except Exception as e|exc` en código de soporte/tests y shim de settings.
- ✅ `surveys/tasks.py` ahora retorna/error_message controlados en fallo de import job por id (sin eco de excepción cruda).
- ✅ Regresión posterior de importación/análisis en verde (15/15).
- ✅ Regresión completa del proyecto en verde (161/161).
- ✅ Sprint C (P2) cerrado técnicamente con regresión completa en verde.

## 1) Objetivos

1. Reducir riesgo de exposición y explotación en producción.
2. Corregir dependencias con vulnerabilidades conocidas.
3. Estandarizar manejo de errores para evitar fuga de información.
4. Mejorar mantenibilidad de vistas grandes sin romper funcionalidad.

## 2) Prioridades (P0 -> P2)

## P0 (inmediato, 24-48h)

- Actualizar dependencias vulnerables en [requirements.txt](../requirements.txt)
  - django: 5.2.9 -> 5.2.11
  - cryptography: 46.0.3 -> 46.0.5
  - werkzeug: 3.1.5 -> 3.1.6
  - weasyprint: 66.0 -> 68.0
  - pillow: 12.0.0 -> 12.1.1
- Sanitizar respuestas de error (no retornar `str(e)` al cliente).
- Restringir `create_checkout_session` a POST y mantener CSRF habilitado.
- Añadir rate limiting a rutas de importación de CSV.

## P1 (corto plazo, 3-7 días)

- Endurecer webhook de Stripe:
  - Verificación de firma (ya existe) + idempotencia persistente por `event.id`.
  - Tolerancia temporal/anti-replay documentada.
- Eliminar fallback de credenciales hardcoded de import test helper.
- Corregir duplicidad de ruta en [surveys/urls.py](../surveys/urls.py).
- Ejecutar regresión completa (tests + smoke de importación, reportes y pagos).

## P2 (mediano plazo, 1-2 semanas)

- Refactor de vistas monolíticas:
  - [surveys/views/import_views.py](../surveys/views/import_views.py)
  - [surveys/views/report_views.py](../surveys/views/report_views.py)
  - [core/views.py](../core/views.py)
- Dividir por casos de uso (services + serializers/validators + handlers).
- Reducir `except Exception` genéricos a excepciones tipadas.
- Hardening Docker: ejecutar como usuario no-root y revisar mínimos privilegios.

## 3) Plan de ejecución por sprint

## Sprint A (P0)

1. Dependencias
   - Editar versiones en [requirements.txt](../requirements.txt).
   - Reinstalar y correr auditoría de CVEs.

2. Error handling seguro
   - Reemplazar mensajes públicos por errores genéricos.
   - Mantener detalle técnico solo en logs.

3. Checkout endpoint
   - Exigir método POST.
   - Mantener autenticación y CSRF.

4. Rate limit import
   - Añadir límites por usuario/IP en endpoints de importación.

5. Verificación
   - Ejecutar tests críticos de imports, reportes y pagos.

## Sprint B (P1)

1. Webhook robustness
2. Limpieza de rutas duplicadas
3. Eliminar credenciales hardcoded de fallback
4. Pruebas de regresión

## Sprint C (P2)

1. Refactor incremental de vistas grandes
2. Reducción de complejidad ciclomática
3. Hardening de contenedor

## 4) Criterios de aceptación

- `pip-audit` sin vulnerabilidades abiertas en dependencias directas.
- Endpoints críticos no exponen excepciones internas al cliente.
- Checkout solo acepta POST y falla correctamente en métodos inválidos.
- Importación protegida por rate limit.
- Sin regresiones en tests relevantes.

## 5) Riesgos y mitigaciones

- Riesgo: ruptura por upgrade de dependencias.
  - Mitigación: upgrade controlado + tests + rollback de lock/versiones.
- Riesgo: cambio de comportamiento en manejo de errores.
  - Mitigación: contratos de respuesta estables (códigos HTTP + estructura JSON).
- Riesgo: refactor amplio en vistas.
  - Mitigación: refactor por módulos pequeños + pruebas por feature.

## 6) Entregables

- PR #1: P0 (dependencias + seguridad endpoints + errores + rate limits)
- PR #2: P1 (webhook robusto + rutas + hardcoded fallback)
- PR #3: P2 (refactor estructural + hardening Docker)

## 7) Siguiente fase operativa (post-remediación)

1. Cierre documental
  - Congelar este plan como baseline de seguridad/remediación.
  - Registrar fecha de cierre técnico y suite de validación final.

2. Empaquetado de cambios por PR lógico
  - PR A: hardening de seguridad (errores sanitizados + logging + Stripe + rate limit).
  - PR B: refactor incremental de vistas/core.
  - PR C: hardening operativo (Docker no-root + utilidades/import/tasks).
  - Estado: agrupación final documentada en [PR_CLOSEOUT_GROUPING.md](PR_CLOSEOUT_GROUPING.md).

3. Checklist de despliegue
  - Validar variables de entorno críticas (`STRIPE_*`, caché, DB, DEBUG=False).
  - Ejecutar smoke tras deploy (Django + Celery + Redis + endpoints críticos).
  - Monitoreo de logs/errores y latencia por 24h.
