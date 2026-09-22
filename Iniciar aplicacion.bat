@echo off
REM Doble clic en este archivo para abrir la aplicacion.
REM Busca Python en el sistema y le pasa el trabajo a iniciar.py.

cd /d "%~dp0"
title SGL - Sistema de Gestion de Licitaciones

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 iniciar.py %*
    goto fin
)

where python >nul 2>&1
if %errorlevel%==0 (
    python iniciar.py %*
    goto fin
)

echo.
echo   ERROR: no se encontro Python en este computador.
echo.
echo   Descargalo desde https://www.python.org/downloads/
echo   IMPORTANTE: durante la instalacion marca la casilla
echo   "Add Python to PATH" o este archivo seguira sin funcionar.
echo.
pause

:fin
