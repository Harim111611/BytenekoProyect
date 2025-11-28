@echo off
echo ========================================
echo Iniciando servidor HTTPS de desarrollo
echo ========================================
echo.
echo Accede a: https://127.0.0.1:8000
echo.
echo IMPORTANTE: Veras una advertencia de "Pagina no segura"
echo Esto es NORMAL en desarrollo. Haz clic en "Avanzado" -^> "Continuar"
echo.
echo ========================================
echo.

python https_server.py

pause

