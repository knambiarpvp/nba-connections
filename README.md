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

### 2. Run the server

**Windows** — double-click `start.bat`, or from a terminal:
```bat
start.bat [GEMINI_API_KEY]
```

**macOS** — first make the scripts executable (one-time step):
```bash
chmod +x start.command start.sh
```
Then double-click `start.command` in Finder, or from a terminal:
```bash
bash start.sh [GEMINI_API_KEY]
```

The launcher will prompt for your API key if you don't pass it as an argument, write it to `.env`, and start the server. Open [http://localhost:5000](http://localhost:5000) in your browser.

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
├── app.py                  # Flask backend — routes, nba_api fetching, Gemini integration
├── templates/
│   └── index.html          # Single-page frontend (HTML + CSS + JS, no build tools)
├── requirements.txt
├── .env                    # Your API key (create this file; gitignored)
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
pip install -r requirements.txt
```

### 3. Configure your API key

```bash
cp .env.example .env
# then edit .env and replace the placeholder with your real key
```

### 4. Run directly

```bash
python app.py                          # default: http://localhost:5000
python app.py --port 8080              # custom port
python start.py AIzaSy...yourkey       # via launcher (writes .env automatically)
```
