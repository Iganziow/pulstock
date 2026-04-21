@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Pulstock Printer Agent - Instalador

echo.
echo ========================================
echo    Pulstock Printer Agent - Instalador
echo ========================================
echo.

REM ─── Paso 1: verificar/instalar Python ────────────────────────
echo [1/4] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo     Python no esta instalado.
    echo     Se abrira la pagina oficial de Python en tu navegador.
    echo.
    echo     IMPORTANTE: al instalar Python, marca la casilla
    echo     "Add Python to PATH" abajo en el instalador.
    echo.
    pause
    start https://www.python.org/downloads/
    echo.
    echo     Despues de instalar Python, ejecuta este archivo de nuevo.
    pause
    exit /b 1
)
echo     OK Python instalado.
echo.

REM ─── Paso 2: instalar dependencias ─────────────────────────────
echo [2/4] Instalando dependencias del agente...
cd /d "%~dp0"
python -m pip install --quiet --upgrade pip >nul 2>&1
python -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo     ERROR: no se pudieron instalar dependencias.
    echo     Revisa tu conexion a internet e intenta de nuevo.
    pause
    exit /b 1
)
echo     OK Dependencias instaladas.
echo.

REM ─── Paso 3: emparejar con la cuenta ───────────────────────────
echo [3/4] Emparejar con tu cuenta Pulstock...
echo.
echo     Se abrira el agente para que escribas tu codigo de emparejado.
echo     El codigo lo obtienes en Pulstock - Configuracion - Impresoras
echo     - Agregar agente PC.
echo.
pause
python pulstock_agent.py --pair
if errorlevel 1 (
    echo.
    echo     ERROR: no se pudo emparejar. Verifica el codigo e intenta de nuevo.
    pause
    exit /b 1
)
echo.
echo     OK Agente emparejado.
echo.

REM ─── Paso 4: registrar auto-inicio ─────────────────────────────
echo [4/4] Configurando inicio automatico con Windows...
set "STARTUP_BAT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\PulstockAgent.bat"
> "!STARTUP_BAT!" (
    echo @echo off
    echo cd /d "%~dp0"
    echo pythonw pulstock_agent.py
)
echo     OK El agente arrancara automaticamente al prender el PC.
echo.

echo ========================================
echo    Instalacion completa!
echo ========================================
echo.
echo    El agente ya esta corriendo en segundo plano.
echo    Puedes cerrar esta ventana.
echo.
echo    Abre Pulstock en tu celular o PC y veras el agente
echo    como "En linea" en Configuracion - Impresoras.
echo.
pause

REM ─── Arrancar el agente en background ─────────────────────────
start "" pythonw pulstock_agent.py
exit /b 0
