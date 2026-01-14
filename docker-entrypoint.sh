#!/bin/bash

# Script de entrada para Docker que asegura que las migraciones se ejecuten
# y la aplicación inicie correctamente

set -e

echo "Esperando que PostgreSQL esté listo..."
while ! nc -z db 5432; do
  sleep 0.1
done
echo "PostgreSQL está listo!"

echo "Verificando estado de las migraciones..."
python manage.py showmigrations --list

if [ "${RUN_MAKEMIGRATIONS:-0}" = "1" ]; then
  echo "Creando migraciones (RUN_MAKEMIGRATIONS=1)..."
  python manage.py makemigrations --noinput
else
  echo "Omitiendo makemigrations (producción segura)."
fi

echo "Aplicando migraciones..."
python manage.py migrate --noinput

echo "Recopilando archivos estáticos..."
python manage.py collectstatic --noinput

echo "Iniciando aplicación..."
exec "$@"
