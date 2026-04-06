"""
NBA Connections — Application Entry Point
Sets up paths, logging, and the Flask app, then delegates to engine and routes.
"""

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

# ─────────────────────────────────────────────────────────────────────────────
# Path helpers for PyInstaller frozen bundles
# Must be set up before load_dotenv() so the right .env file is found.
# ─────────────────────────────────────────────────────────────────────────────

def _get_base_path() -> Path:
    """Resources directory: sys._MEIPASS when frozen, else next to this file."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).parent


def _get_writable_path() -> Path:
    """Writable directory: next to the .exe when frozen, else next to this file."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


BASE_PATH = _get_base_path()
WRITABLE_PATH = _get_writable_path()

load_dotenv(WRITABLE_PATH / "secret" / ".env")

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(message)s",
    datefmt="%H:%M:%S",
)

# ─────────────────────────────────────────────────────────────────────────────
# Flask app
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__, template_folder=str(BASE_PATH / "templates"))

from routes import blueprint  # noqa: E402 — imported after app to avoid issues with frozen bundles
app.register_blueprint(blueprint)

# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse as _argparse

    _parser = _argparse.ArgumentParser(add_help=False)
    _parser.add_argument("--host", default="127.0.0.1")
    _parser.add_argument("--port", type=int, default=5000)
    _args, _ = _parser.parse_known_args()

    # Disable debug mode and reloader when running as a frozen executable
    _debug = not getattr(sys, "frozen", False)
    app.run(debug=_debug, use_reloader=_debug, host=_args.host, port=_args.port)

