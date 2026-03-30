#!/usr/bin/env bash
# NBA Connections — macOS double-click launcher
# This file opens in Terminal when double-clicked in Finder.
# To enable: run once in Terminal:  chmod +x src/start.command src/start.sh

cd "$(dirname "$0")" || exit 1
bash start.sh "$@"

echo ""
read -r -p "Server stopped. Press Enter to close this window..."
