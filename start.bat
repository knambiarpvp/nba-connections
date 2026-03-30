@echo off
:: NBA Connections — Windows launcher
:: Double-click this file to start the server.

cd /d "%~dp0"

:: Use the venv Python if it exists, otherwise fall back to system Python
if exist "venv\Scripts\python.exe" (
    set PYTHON=venv\Scripts\python.exe
) else (
    set PYTHON=python
)

:: Check Python is available
%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+ and run:
    echo   python -m venv venv
    echo   venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

%PYTHON% start.py %*

pause
