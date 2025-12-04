# Settings - Configuración por Entorno

Este directorio contiene archivos de configuración de Django para diferentes entornos.

## Archivos

- **base.py**: Configuración base compartida entre todos los entornos
- **development.py**: Configuración para desarrollo local
- **production.py**: Configuración para producción

## Uso

La configuración se selecciona mediante la variable de entorno `DJANGO_SETTINGS_MODULE`:

```bash
# Desarrollo
export DJANGO_SETTINGS_MODULE=byteneko.settings.development
python manage.py runserver

# Producción
export DJANGO_SETTINGS_MODULE=byteneko.settings.production
gunicorn byteneko.wsgi:application
```

## Variables de Entorno

Cada entorno puede tener variables diferentes definidas en `.env`:

- `DEBUG`: Modo debug (True/False)
- `SECRET_KEY`: Clave secreta
- `ALLOWED_HOSTS`: Hosts permitidos
- `DATABASE_URL`: URL de base de datos
- `REDIS_URL`: URL de Redis

## Configuración por Entorno

### Development
- DEBUG = True
- ALLOWED_HOSTS = ['localhost', '127.0.0.1']
- Base de datos local (SQLite o PostgreSQL local)
- Logging en consola

### Production
- DEBUG = False
- ALLOWED_HOSTS desde .env
- PostgreSQL en servidor remoto
- Logging en archivos
- Security headers activados
- HTTPS obligatorio

## Estructura Recomendada

```
settings/
├── __init__.py
├── base.py          # Configuración compartida
├── development.py   # Desarrollo
├── production.py    # Producción
└── testing.py       # Testing (opcional)
```
