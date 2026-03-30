@echo off
:: Build script for NBA Connections (Windows)
:: Run from anywhere — outputs to <project-root>\dist\nba-connections\
:: No Python required on the target machine.

setlocal

:: Move to this script's directory (src\compile\)
cd /d "%~dp0"

echo ============================================================
echo  NBA Connections ^— Windows Build
echo ============================================================
echo.

:: Prefer the project venv (two levels up) if it exists
if exist "..\..\venv\Scripts\python.exe" (
    set PYTHON="..\..\venv\Scripts\python.exe"
) else (
    set PYTHON=python
)

echo [1/2] Installing / upgrading PyInstaller...
%PYTHON% -m pip install --quiet --upgrade pyinstaller
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller.
    pause
    exit /b 1
)

echo [2/2] Building executable...
%PYTHON% -m PyInstaller --clean --noconfirm --distpath ..\..\dist --workpath ..\..\build nba_connections.spec
if errorlevel 1 (
    echo ERROR: Build failed.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Build complete!
echo  Executable: dist\nba-connections\nba-connections.exe
echo.
echo  To distribute: zip the entire dist\nba-connections\ folder.
echo  Users run nba-connections.exe ^— no Python required.
echo ============================================================
echo.
pause
