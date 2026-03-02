# Deploy Checklist — Post Security Remediation

Fecha: 2026-03-01

## 1) Pre-deploy

- Confirmar `DEBUG=False` en entorno objetivo.
- Confirmar `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` correctos.
- Confirmar secretos/llaves:
  - `STRIPE_SECRET_KEY`
  - `STRIPE_WEBHOOK_SECRET`
  - `STRIPE_WEBHOOK_TOLERANCE`
- Confirmar conectividad y credenciales:
  - Base de datos
  - Redis/cache
  - Broker Celery

## 2) Runtime hardening

- Verificar contenedor corriendo como usuario no-root.
- Verificar permisos de escritura solo en rutas necesarias.
- Confirmar healthcheck de aplicación y worker.

## 3) Migraciones y arranque

- Ejecutar migraciones Django.
- Iniciar servicios:
  - Redis
  - Celery worker
  - Django app
- Confirmar que no hay errores de importación de módulos críticos.

## 4) Smoke post-deploy

- Login y dashboard.
- Flujo de importación CSV (preview + start + status).
- Endpoints de reportes (preview/export).
- Checkout (`POST`) y recepción de webhook Stripe (`POST`, firma válida).

## 5) Observabilidad (24h)

- Revisar errores 5xx y excepciones no controladas.
- Revisar latencia en endpoints críticos de import/report.
- Revisar cola Celery (tareas fallidas/reintentos).
- Validar ausencia de payloads sensibles en logs.

## 6) Criterio de éxito

- Sin regresiones funcionales críticas.
- Sin exposición de errores internos en respuestas de API.
- Procesos async estables y sin crecimiento anómalo de memoria.
