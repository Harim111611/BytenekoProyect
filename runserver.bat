@echo off
echo ========================================
echo Iniciando servidor Django con runserver
echo ========================================
echo.
echo Accede a: http://localhost:8001
echo (Puerto 8001 para evitar problemas de HSTS)
echo.
echo Los logs de DELETE apareceran aqui con el prefijo [DELETE]
echo Presiona Ctrl+C para detener el servidor
echo ========================================
echo.

python manage.py runserver localhost:8001
