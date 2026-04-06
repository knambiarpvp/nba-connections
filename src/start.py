"""
NBA Connections — launcher script.

Usage:
    python start.py                        # prompts for API key
    python start.py <GEMINI_API_KEY>       # pass key directly
    python start.py --port 8080            # optional port (default: 5000)

The script writes (or replaces) the .env file with the provided key,
then starts the Flask development server.
"""

import argparse
import getpass
import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path


def _exe_dir() -> Path:
    """Directory that contains the executable (frozen) or this file (dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent  # src/


ENV_FILE = _exe_dir() / "secret" / ".env"
APP_FILE = Path(__file__).parent / "app.py"


def write_env(api_key: str) -> None:
    contents = (
        "# Get your free Gemini API key at https://aistudio.google.com/app/apikey\n"
        f"GEMINI_API_KEY={api_key}\n"
    )
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text(contents, encoding="utf-8")
    print(f"  .env written to {ENV_FILE}")


def get_api_key(args_key: str | None) -> str:
    if args_key:
        return args_key.strip()

    # Check if .env already has a real key and offer to reuse it
    existing_key = ""
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("GEMINI_API_KEY="):
                existing_key = line.split("=", 1)[1].strip()
                break

    if existing_key and existing_key != "your_gemini_api_key_here":
        masked = existing_key[:8] + "..." + existing_key[-4:]
        answer = input(f"\n  Existing API key found ({masked}). Use it? [Y/n]: ").strip().lower()
        if answer in ("", "y", "yes"):
            return existing_key

    print("\n  Get a free key at: https://aistudio.google.com/app/apikey")
    key = getpass.getpass("  Enter your Gemini API key: ").strip()
    if not key:
        print("  ERROR: API key cannot be empty.", file=sys.stderr)
        sys.exit(1)
    return key


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Start the NBA Connections Flask server.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "api_key",
        nargs="?",
        metavar="GEMINI_API_KEY",
        help="Your Gemini API key (omit to be prompted)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port to run the server on (default: 5000)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    args = parser.parse_args()

    print("=" * 55)
    print("  NBA Connections — Server Launcher")
    print("=" * 55)

    api_key = get_api_key(args.api_key)
    write_env(api_key)

    # Also inject into the current process so the Flask app sees it immediately
    # (avoids relying on load_dotenv re-reading .env after process start)
    os.environ["GEMINI_API_KEY"] = api_key

    print(f"\n  Starting Flask server on http://{args.host}:{args.port}")
    print("  Press Ctrl+C to stop.\n")

    # Open the browser shortly after the server starts.
    # 1.5 s is enough for Flask to bind the socket before the tab tries to connect.
    url = f"http://{args.host}:{args.port}"
    threading.Timer(1.5, webbrowser.open, args=[url]).start()

    try:
        if getattr(sys, "frozen", False):
            # Running as a PyInstaller bundle — import and run Flask directly.
            # app.py is bundled; we cannot subprocess it as a separate file.
            try:
                from app import app as flask_app  # type: ignore[import]
                flask_app.run(debug=False, use_reloader=False, host=args.host, port=args.port)
            except Exception as exc:
                print(f"\n  ERROR: {exc}", file=sys.stderr)
                input("\n  Press Enter to close...")
                sys.exit(1)
        else:
            # Development mode — run app.py as a subprocess.
            env = os.environ.copy()
            subprocess.run(
                [sys.executable, str(APP_FILE), "--host", args.host, "--port", str(args.port)],
                env=env,
                check=False,
            )
    except KeyboardInterrupt:
        print("\n  Server stopped.")


if __name__ == "__main__":
    main()
