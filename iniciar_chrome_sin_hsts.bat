@echo off
echo ========================================
echo Iniciando Chrome sin HSTS
echo ========================================
echo.
echo Esto abrira Chrome con HSTS deshabilitado
echo Cierra esta ventana cuando termines
echo ========================================
echo.

start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --disable-web-security --user-data-dir="%TEMP%\chrome_dev_session" --disable-features=HSTS

