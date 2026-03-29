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

### 1. Prerequisites

- Python 3.10+
- A free Google Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey)

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# Windows (Git Bash / PowerShell)
source venv/Scripts/activate   # Git Bash
.\venv\Scripts\Activate.ps1    # PowerShell

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure your API key

Create a .env file at the root of this repository and copy the free Google Gemini API key you generated from [Google AI Studio](https://aistudio.google.com/app/apikey) into the .env file.

```
# Get your free Gemini API key at https://aistudio.google.com/app/apikey
GEMINI_API_KEY=your_gemini_api_key_here

# Optional: Flask settings
FLASK_ENV=development
FLASK_DEBUG=1
```


### 5. Run the server

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser.

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

