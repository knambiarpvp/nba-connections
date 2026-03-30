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
from pathlib import Path

ENV_FILE = Path(__file__).parent / ".env"
APP_FILE = Path(__file__).parent / "app.py"


def write_env(api_key: str) -> None:
    contents = (
        "# Get your free Gemini API key at https://aistudio.google.com/app/apikey\n"
        f"GEMINI_API_KEY={api_key}\n"
    )
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

    print(f"\n  Starting Flask server on http://{args.host}:{args.port}")
    print("  Press Ctrl+C to stop.\n")

    # Run app.py with the same Python interpreter that's running this script,
    # passing host/port via environment variables read by Flask.
    env = os.environ.copy()
    env["FLASK_RUN_HOST"] = args.host
    env["FLASK_RUN_PORT"] = str(args.port)

    try:
        subprocess.run(
            [sys.executable, str(APP_FILE), "--host", args.host, "--port", str(args.port)],
            env=env,
            check=False,
        )
    except KeyboardInterrupt:
        print("\n  Server stopped.")


if __name__ == "__main__":
    main()
