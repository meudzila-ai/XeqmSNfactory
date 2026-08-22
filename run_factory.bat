@echo off
title XeQM SN Factory Launcher - Debug Mode
echo ==========================================
echo    XeQM SN Factory: Diagnostic Launch
echo ==========================================

:: Set the file to be launched
set LAUNCH_FILE=ui.py

if not exist %LAUNCH_FILE% (
    echo [ERROR] File %LAUNCH_FILE% not found!
    echo Please check if your file is named ui.py
    pause
    exit
)

:: Check libraries before launching
echo [INFO] Checking Python environment...
python -c "import requests, yaml" >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Missing libraries! Please run install_requirements.bat
    pause
)

echo [INFO] Launching program: %LAUNCH_FILE%
echo ------------------------------------------
:: Launch and prevent the window from closing immediately
python %LAUNCH_FILE%

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] The program closed with an error (code %errorlevel%)
)
echo.
echo Press any key to close this window.
pause