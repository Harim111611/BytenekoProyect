#!/bin/bash
echo "========================================"
echo "Iniciando servidor Django con runserver"
echo "========================================"
echo ""
echo "Los logs de DELETE aparecerán aquí con el prefijo [DELETE]"
echo "Presiona Ctrl+C para detener el servidor"
echo "========================================"
echo ""

python manage.py runserver 127.0.0.1:8000

