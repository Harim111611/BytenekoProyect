# Deploy en AWS EC2 (Docker Compose)

## Archivos
- Usa `docker-compose.prod.yml` para producción.
- Crea `.env.prod` en el servidor (a partir de `.env.prod.example`).

## Pasos mínimos
1. En EC2 (Ubuntu/Debian), instala Docker + Docker Compose plugin.
2. Clona el repo en una ruta estable (ej. `/opt/byteneko`).
3. Crea el archivo de entorno:
   - `cp .env.prod.example .env.prod`
   - Edita valores: `SECRET_KEY`, `ALLOWED_HOSTS`, DB/Redis.
4. Levanta servicios:
   - `docker compose -f docker-compose.prod.yml up -d --build`

## Verificación rápida
- Checks de despliegue Django:
  - `docker compose -f docker-compose.prod.yml exec django python manage.py check --deploy`
- Migraciones:
  - `docker compose -f docker-compose.prod.yml exec django python manage.py migrate --noinput`

## SECRET_KEY (importante)
En contenedores con Docker Compose, algunos valores con `$` pueden disparar warnings de interpolación (por ejemplo: "The \"u\" variable is not set").
Para evitarlo:
- Usa una clave sin `$` (recomendado), o
- Escapa cada `$` como `$$`.

Generar una clave segura sin `$`:
- `python -c "import secrets; print(secrets.token_urlsafe(64))"`

Si necesitas correr `check --deploy` sin usar `manage.py`:
- `python -c "import os, django; os.environ.setdefault('DJANGO_SETTINGS_MODULE','byteneko.settings'); django.setup(); from django.core.management import call_command; call_command('check','--deploy')"`

## Nota sobre contraseñas de Postgres
Postgres solo usa `POSTGRES_USER/POSTGRES_PASSWORD` (aquí derivadas de `DB_USER/DB_PASSWORD`) la primera vez que inicializa el volumen.
Si cambias `DB_PASSWORD` después de que el volumen ya existe, verás errores de “password authentication failed”.

En un entorno de prueba sin datos importantes, puedes reiniciar la base de datos borrando el volumen:
- `docker-compose -f docker-compose.prod.yml --env-file .env.prod down -v`
- `docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d --build`

## HTTPS
En producción, termina TLS con:
- ALB (recomendado) + ACM, o
- Nginx/Caddy en la EC2 con Let's Encrypt.

Tu settings de producción usa `SECURE_SSL_REDIRECT=True`, así que necesitas servir HTTPS (directo o vía proxy) para no caer en redirecciones/errores.
