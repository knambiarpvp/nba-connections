# NBA Connections

A spinoff of the NYT Connections puzzle game that uses 16 NBA players split into 4 hidden-connection groups — powered by the `nba_api` library and Google Gemini AI.

---

## Features

- **Active or All-Time player pool** — toggle between current-season players and NBA legends
- **AI-generated puzzles** — Google Gemini (`gemini-2.5-flash`) analyses real player metadata (teams, college, draft class, jersey number, country, position) to create 4 groups of 4 with increasing difficulty
- **Authentic Connections UX** — tile selection, shuffle, deselect, mistake tracking (4 lives), "One away…" hint, animated correct/incorrect feedback, end-of-game reveal
- **Server-side validation** — puzzle answers are never sent to the browser; all guesses validated on the backend
- **Player data cache** — NBA stats are cached locally (`players_cache.json`) for 24 hours to avoid repeated rate-limited calls to stats.nba.com

---

## Setup

### 1. Get a free Gemini API key

Create a free key at [Google AI Studio](https://aistudio.google.com/app/apikey).

### 2. Download the latest release

Go to the [Releases page](../../releases/latest) and download the zip for your platform:

| File                          | Platform                                          |
| ----------------------------- | ------------------------------------------------- |
| `nba-connections-windows.zip` | Windows x86_64                                    |
| `nba-connections-macos.zip`   | macOS arm64 (Apple Silicon + Intel via Rosetta 2) |

Unzip, then run the executable inside the folder.

### 3. Run the server

**Windows** — double-click `nba-connections.exe`, or from a terminal:
```bat
nba-connections.exe [GEMINI_API_KEY]
```

**macOS** — clear the Gatekeeper quarantine flag once after unzipping:
```bash
xattr -cr nba-connections/
```
Then run:
```bash
./nba-connections/nba-connections [GEMINI_API_KEY]
```

The `nba-connections-macos.zip` is built for **arm64**. It runs natively on Apple Silicon and automatically via Rosetta 2 on Intel Macs (no extra steps needed).

The executable will prompt for your Gemini API key if not provided, save it to `.env` next to the executable, and start the server. Open [http://localhost:5000](http://localhost:5000) in your browser.

> **Note — source launchers:** If you have Python installed, `src/start/start.bat` (Windows) and `src/start/start.command`/`src/start/start.sh` (macOS) work the same way without needing a release build. See [Development Setup](#development-setup).

---

## How to Play

1. Choose **Active Players** (current season) or **All-Time Legends**
2. Click **🎲 New Puzzle** — Gemini will fetch player data and generate a puzzle (takes ~30–90 seconds on first run while player data is fetched; subsequent runs are faster due to caching)
3. Select 4 players you think share a hidden connection, then click **Submit**
4. Correct → the group is revealed with its category name and explanation
5. Wrong → you lose a life (4 total). If 3 of your 4 picks were right, you'll see "One away…"
6. Solve all 4 groups to win!

**Difficulty colours:**

| Colour   | Level    |
| -------- | -------- |
| 🟨 Yellow | Easiest  |
| 🟩 Green  | Moderate |
| 🟦 Blue   | Hard     |
| 🟪 Purple | Hardest  |

---

## Project Structure

```
nba-connections/
├── src/
│   ├── app.py              # Flask backend — routes, nba_api fetching, Gemini integration
│   ├── .env                # Your API key (created automatically; gitignored)
│   ├── start/
│   │   ├── start.py        # Cross-platform launcher (API key prompt, writes .env)
│   │   ├── start.bat       # Windows launcher
│   │   ├── start.sh        # macOS/Linux launcher
│   │   └── start.command   # macOS Finder double-click launcher
│   ├── compile/
│   │   ├── build.bat       # Windows build script (produces standalone .exe)
│   │   ├── build.sh        # macOS/Linux build script
│   │   ├── nba_connections.spec  # PyInstaller spec file
│   │   └── requirements.txt
│   └── templates/
│       └── index.html      # Single-page frontend (HTML + CSS + JS, no build tools)
├── .github/
│   └── workflows/
│       └── release.yml     # CI: builds executables and publishes GitHub Releases
├── .gitignore
└── players_cache.json      # Auto-generated player data cache (gitignored)
```

---

## Tech Stack

| Layer                | Technology                                                      |
| -------------------- | --------------------------------------------------------------- |
| Backend              | Python 3.10+, Flask 3                                           |
| Player data          | [`nba_api`](https://github.com/swar/nba_api)                    |
| AI puzzle generation | Google Gemini `gemini-2.5-flash` (free tier) via `google-genai` |
| Schema / validation  | Pydantic v2 (structured Gemini output)                          |
| Frontend             | Vanilla HTML/CSS/JS (no framework, no build step)               |

---

## CI/CD — Automated Releases

Every merge to `main` triggers the [Build and Release](.github/workflows/release.yml) GitHub Actions workflow, which:

1. Determines the next [semantic version](https://semver.org) from commit messages using [Conventional Commits](https://www.conventionalcommits.org)
2. Builds executables in parallel on Windows (`windows-latest`) and macOS (`macos-latest`, universal2)
3. Creates a [GitHub Release](../../releases) with the new tag and attaches both zips

**Version bump rules (commit message prefix):**

| Prefix                               | Bump            |
| ------------------------------------ | --------------- |
| `feat:`                              | Minor (`1.x.0`) |
| `fix:`, `chore:`, etc.               | Patch (`1.0.x`) |
| `feat!:` or `BREAKING CHANGE` footer | Major (`x.0.0`) |
| _(anything else)_                    | Patch           |

---

## Building Standalone Executables (No Python Required)

Use [PyInstaller](https://pyinstaller.org) to bundle Python and all dependencies into a self-contained executable that can be distributed to machines with no Python installed.

### Prerequisites

- Python 3.10+ and the project's virtual environment set up (see [Development Setup](#development-setup) below)
- Dependencies installed (`pip install -r requirements.txt`)

### Build

**Windows** — double-click `src\compile\build.bat`, or from a terminal:
```bat
src\compile\build.bat
```

**macOS / Linux:**
```bash
chmod +x src/compile/build.sh
src/compile/build.sh
```

The build output is placed in `dist/nba-connections/`. To distribute, zip the **entire `dist/nba-connections/` folder** — the executable plus its support files must stay together.

### Running the built executable

**Windows:**
```bat
dist\nba-connections\nba-connections.exe [GEMINI_API_KEY]
```

**macOS / Linux:**
```bash
./dist/nba-connections/nba-connections [GEMINI_API_KEY]
```

The executable behaves identically to `python start.py`: it prompts for your Gemini API key if not provided, writes `.env` next to the executable, and starts the server.

### macOS notes

- **Gatekeeper warning** — macOS will block unsigned executables downloaded from the internet. Before running, clear the quarantine flag on the unzipped folder:
  ```bash
  xattr -cr nba-connections/
  ```
  Alternatively, right-click the executable in Finder and choose **Open**.
- **Intel Macs** — the binary is arm64 and runs via Rosetta 2, which is installed by default on all Apple Silicon Macs. Intel Mac users can run it without any changes.

> **Note:** The first build can take several minutes and produces a large folder (~150–300 MB) because it bundles a full Python runtime. Subsequent builds are faster due to caching.

---

## Development Setup

If you want to modify the code or run the server manually without the launcher scripts, you'll need Python 3.10+ and a virtual environment.

### 1. Create and activate a virtual environment

```bash
python -m venv venv

# Windows (Git Bash)
source venv/Scripts/activate
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# macOS / Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r src/compile/requirements.txt
```

### 3. Configure your API key

```bash
# Manually create src/.env with your Gemini API key:
echo "GEMINI_API_KEY=your_key_here" > src/.env
```

### 4. Run directly

```bash
python src/app.py                          # default: http://localhost:5000
python src/app.py --port 8080              # custom port
python src/start/start.py AIzaSy...yourkey       # via launcher (writes src/.env automatically)
```

Or use the shell launchers from the project root:

```bash
# macOS / Linux (one-time chmod)
chmod +x src/start/start.sh src/start/start.command
bash src/start/start.sh [GEMINI_API_KEY]
```

```bat
rem Windows
src\start\start.bat [GEMINI_API_KEY]
```
