@echo off
title Setup Dependencies - XeQM SN Factory 
echo ==========================================
echo    XeQM SN Factory: Dependency Setup
echo ==========================================
echo.

:: Checking Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    py --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Python is not installed!
        echo Please download it from https://www.python.org
        pause
        exit
    )
)

echo [OK] Python found.
echo [INFO] Installing required libraries: requests, pyyaml, psutil...
echo.

:: Upgrading pip and installing required libraries
python -m pip install --upgrade pip
pip install requests pyyaml psutil

echo.
echo ==========================================
echo [SUCCESS] All dependencies installed!
echo You can now launch the Factory via run_factory.bat
echo ==========================================
pause