# Byteneko - Configuración del Proyecto Django

Este directorio contiene la configuración central del proyecto Django.

## Estructura

- **settings/**: Directorio con configuraciones de entorno
  - `base.py`: Configuración base compartida
  - `development.py`: Configuración para desarrollo
  - `production.py`: Configuración para producción

- **settings_production.py**: Configuración específica para producción (legacy)
- **settings_test.py**: Configuración para entorno de testing

- **asgi.py**: Punto de entrada ASGI para servidores web asincronos
- **wsgi.py**: Punto de entrada WSGI para servidores web tradicionales

- **celery.py**: Configuración de Celery para tareas asincrónicas
- **urls.py**: Enrutamiento principal del proyecto
- **views.py**: Vistas generales o de utilidad del proyecto

- **__init__.py**: Inicializador del paquete Django

## Configuración

### Variables de Entorno

Las variables de entorno se cargan desde `.env` usando `python-decouple`:
- `DEBUG`: Modo debug (True/False)
- `SECRET_KEY`: Clave secreta de Django
- `ALLOWED_HOSTS`: Hosts permitidos
- `DATABASE_URL`: URL de conexión a PostgreSQL
- `REDIS_URL`: URL de conexión a Redis
- `CELERY_BROKER_URL`: URL del broker de Celery

### Puntos de Entrada

- **ASGI**: Para aplicaciones asincronizadas (FastAPI, WebSockets)
- **WSGI**: Para aplicaciones sincronizadas (Gunicorn, uWSGI)

## Ejecución

```bash
# Desarrollo
python manage.py runserver

# Producción (WSGI)
gunicorn byteneko.wsgi:application

# Celery Worker
celery -A byteneko worker -l info

# Celery Beat (scheduler)
celery -A byteneko beat -l info
```
