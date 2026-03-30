#!/usr/bin/env bash
# NBA Connections — macOS/Linux launcher
# Double-click start.command in Finder, or run: bash start.sh [GEMINI_API_KEY] [--port PORT]

# Change to the directory containing this script (important for Finder double-click)
cd "$(dirname "$0")" || exit 1

# ── Find Python ──────────────────────────────────────────────────────────────
if [ -f "venv/bin/python" ]; then
    PYTHON="venv/bin/python"
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
if [ ! -f "venv/bin/python" ]; then
    echo "Virtual environment not found."
    read -r -p "Create it now and install dependencies? [Y/n]: " answer
    answer="${answer:-y}"
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        echo "Creating virtual environment..."
        $PYTHON -m venv venv || { echo "ERROR: Failed to create venv."; exit 1; }
        echo "Installing dependencies..."
        venv/bin/pip install -r requirements.txt || { echo "ERROR: pip install failed."; exit 1; }
        PYTHON="venv/bin/python"
        echo ""
    else
        echo "Skipping venv setup. Using system Python."
    fi
fi

# ── Launch ────────────────────────────────────────────────────────────────────
$PYTHON start.py "$@"
