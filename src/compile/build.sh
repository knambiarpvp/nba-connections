#!/usr/bin/env bash
# Build script for NBA Connections (macOS / Linux)
# Run from anywhere — outputs to <project-root>/dist/nba-connections/
# No Python required on the target machine.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo " NBA Connections — macOS/Linux Build"
echo "============================================================"
echo

# Prefer the project venv (in project root) if it exists
if [[ -x "$PROJECT_ROOT/venv/bin/python" ]]; then
    PYTHON="$PROJECT_ROOT/venv/bin/python"
else
    PYTHON="python3"
fi

echo "[1/2] Installing / upgrading PyInstaller..."
"$PYTHON" -m pip install --quiet --upgrade pyinstaller

echo "[2/2] Building executable..."
"$PYTHON" -m PyInstaller --clean --noconfirm \
    --distpath "$PROJECT_ROOT/dist" \
    --workpath "$PROJECT_ROOT/build" \
    nba_connections.spec

echo
echo "============================================================"
echo " Build complete!"
echo " Executable: dist/nba-connections/nba-connections"
echo
echo " To distribute: zip the entire dist/nba-connections/ folder."
echo " Users run ./nba-connections — no Python required."
echo "============================================================"
echo
