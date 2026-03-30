@echo off
:: NBA Connections — Windows launcher
:: Run from the src\start\ directory or double-click from there.

cd /d "%~dp0"

:: Use the venv Python (two levels up in project root) if it exists
if exist "..\..\venv\Scripts\python.exe" (
    set PYTHON=..\..\venv\Scripts\python.exe
) else (
    set PYTHON=python
)

:: Check Python is available
%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+ and run:
    echo   python -m venv venv
    echo   venv\Scripts\pip install -r src\build\requirements.txt
    pause
    exit /b 1
)

%PYTHON% start.py %*

pause
