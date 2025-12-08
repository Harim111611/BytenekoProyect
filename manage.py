#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from decouple import config

def main():
    """Run administrative tasks."""
    # 1. Obtener el entorno actual ('local' por defecto)
    # Usamos decouple o os.environ directamente si decouple falla al inicio
    try:
        env_state = config('DJANGO_ENV', default='local')
    except:
        env_state = os.environ.get('DJANGO_ENV', 'local')

    # 2. Configurar el módulo de settings correcto basado en el entorno
    # Si es 'local', cargará 'byteneko.settings.local'
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', f'byteneko.settings.{env_state}')

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    # Safety: if user runs `manage.py runserver` without host:port,
    # bind to localhost only to avoid exposing the development server.
    if 'runserver' in sys.argv and not any(':' in a or a == '0.0.0.0' for a in sys.argv[1:]):
        # If no address specified, default to localhost:8010
        sys.argv.append('127.0.0.1:8010')
    main()