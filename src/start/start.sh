#!/usr/bin/env bash
# NBA Connections — macOS/Linux launcher
# Run: bash src/start.sh [GEMINI_API_KEY] [--port PORT]
# Or double-click src/start.command in Finder.

# Change to the directory containing this script (src/)
cd "$(dirname "$0")" || exit 1

PROJECT_ROOT="$(cd ../.. && pwd)"

# ── Find Python ──────────────────────────────────────────────────────────────
if [ -f "$PROJECT_ROOT/venv/bin/python" ]; then
    PYTHON="$PROJECT_ROOT/venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo "ERROR: Python not found."
    echo "Install Python 3.10+ from https://www.python.org/downloads/"
    echo ""
    read -r -p "Press Enter to close..."
    exit 1
fi

# ── Check venv exists, offer to create it ────────────────────────────────────
if [ ! -f "$PROJECT_ROOT/venv/bin/python" ]; then
    echo "Virtual environment not found."
    read -r -p "Create it now and install dependencies? [Y/n]: " answer
    answer="${answer:-y}"
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        echo "Creating virtual environment..."
        $PYTHON -m venv "$PROJECT_ROOT/venv" || { echo "ERROR: Failed to create venv."; exit 1; }
        echo "Installing dependencies..."
        "$PROJECT_ROOT/venv/bin/pip" install -r ../build/requirements.txt || { echo "ERROR: pip install failed."; exit 1; }
        PYTHON="$PROJECT_ROOT/venv/bin/python"
        echo ""
    else
        echo "Skipping venv setup. Using system Python."
    fi
fi

# ── Launch ────────────────────────────────────────────────────────────────────
$PYTHON start.py "$@"
