"""
NBA Connections - Backend
Flask API + nba_api data fetching + Gemini puzzle generation
"""

import json
import logging
import os
import random
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from pydantic import BaseModel, Field

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

app = Flask(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Gemini client setup
# ─────────────────────────────────────────────────────────────────────────────

def get_gemini_client():
    """Return a configured Gemini client, raising a clear error if key is missing."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_gemini_api_key_here":
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Set GEMINI_API_KEY in your environment or "
            ".env file with a key from https://aistudio.google.com/app/apikey"
        )
    from google import genai  # lazy import so startup works without key
    return genai.Client(api_key=api_key)


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schemas for Gemini structured output
# ─────────────────────────────────────────────────────────────────────────────

class PlayerGroup(BaseModel):
    category: str = Field(
        description="Short, specific label for the shared connection (2-6 words, e.g. 'DRAFTED BY SPURS', 'PLAYED AT DUKE', 'WORE #23')"
    )
    players: list[str] = Field(
        description="Exactly 4 NBA player full names from the provided list, spelled exactly as given",
        min_length=4,
        max_length=4,
    )
    difficulty: int = Field(
        description="Difficulty level: 1 = easiest/most obvious, 4 = hardest/most obscure. Each level used exactly once.",
        ge=1,
        le=4,
    )
    connection_explanation: str = Field(
        description="One sentence factual explanation of why these 4 players share this connection"
    )


class PuzzleResponse(BaseModel):
    groups: list[PlayerGroup] = Field(
        description="Exactly 4 groups. All 16 provided players must appear, each in exactly one group.",
        min_length=4,
        max_length=4,
    )


# ─────────────────────────────────────────────────────────────────────────────
# In-memory puzzle store  { puzzle_id: puzzle_data_dict }
# ─────────────────────────────────────────────────────────────────────────────

PUZZLE_TTL_MINUTES = 60


class ExpiringPuzzleStore(dict):
    """
    Dict-like store that automatically expires puzzles older than PUZZLE_TTL_MINUTES.

    Internally stores each value as {"value": puzzle_dict, "created_at": datetime}.
    Public API remains dict[str, dict]-like: reads/writes use only the puzzle_dict.
    """

    def __init__(self, *args, ttl_minutes: int = PUZZLE_TTL_MINUTES, **kwargs):
        self.ttl = timedelta(minutes=ttl_minutes)
        super().__init__(*args, **kwargs)

    def _cleanup(self) -> None:
        """Remove entries older than the configured TTL."""
        if not super().__len__():
            return
        now = datetime.now()
        keys_to_delete = []
        for key, wrapped in super().items():
            created_at = wrapped.get("created_at")
            if not isinstance(created_at, datetime):
                continue
            if now - created_at > self.ttl:
                keys_to_delete.append(key)
        for key in keys_to_delete:
            super().pop(key, None)

    def __setitem__(self, key, value) -> None:
        self._cleanup()
        wrapped = {"value": value, "created_at": datetime.now()}
        super().__setitem__(key, wrapped)

    def __getitem__(self, key):
        self._cleanup()
        wrapped = super().__getitem__(key)
        return wrapped.get("value")

    def get(self, key, default=None):
        self._cleanup()
        wrapped = super().get(key)
        if wrapped is None:
            return default
        return wrapped.get("value", default)

    def __contains__(self, key) -> bool:
        self._cleanup()
        return super().__contains__(key)

    def items(self):
        self._cleanup()
        for key, wrapped in super().items():
            yield key, wrapped.get("value")

    def values(self):
        self._cleanup()
        for wrapped in super().values():
            yield wrapped.get("value")

    def keys(self):
        self._cleanup()
        return super().keys()

    def pop(self, key, default=None):
        self._cleanup()
        wrapped = super().pop(key, None)
        if wrapped is None:
            return default
        return wrapped.get("value", default)

    def __iter__(self):
        self._cleanup()
        return super().__iter__()

    def __len__(self) -> int:
        self._cleanup()
        return super().__len__()


_puzzles: dict[str, dict] = ExpiringPuzzleStore(ttl_minutes=PUZZLE_TTL_MINUTES)
DIFFICULTY_COLORS = {1: "yellow", 2: "green", 3: "blue", 4: "purple"}
DIFFICULTY_HEX = {1: "#f9df6d", 2: "#a0c35a", 3: "#b0c4ef", 4: "#ba81c5"}


# ─────────────────────────────────────────────────────────────────────────────
# Player data fetching
# ─────────────────────────────────────────────────────────────────────────────

CACHE_FILE = Path(__file__).parent / "players_cache.json"
CACHE_TTL_HOURS = 24


def _cache_is_fresh(cache: dict, pool: str) -> bool:
    key = f"{pool}_fetched_at"
    if key not in cache:
        return False
    fetched = datetime.fromisoformat(cache[key])
    return datetime.now() - fetched < timedelta(hours=CACHE_TTL_HOURS)


def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_cache(cache: dict) -> None:
    try:
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # non-fatal


def _nba_request_with_retry(fn, *args, retries: int = 3, base_delay: float = 2.0, **kwargs):
    """
    Call an nba_api endpoint constructor with exponential-backoff retries.
    Raises the last exception if all retries fail.
    """
    for attempt in range(1, retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if attempt == retries:
                raise
            wait = base_delay * (2 ** (attempt - 1))
            log.warning("[retry] Attempt %d/%d failed (%s). Waiting %.0fs ...", attempt, retries, exc, wait)
            time.sleep(wait)


def fetch_players_with_metadata(pool: str = "active") -> list[dict]:
    """
    Fetch player bio data using a single bulk PlayerIndex call per season instead of
    one API call per player. This reduces ~1060 requests down to 1-4 requests, avoiding
    stats.nba.com rate-limit timeouts.

    Career team history is NOT fetched here — it is fetched for only the 16 selected
    players in enrich_with_career_teams(), keeping total API calls very low.
    """
    cache = load_cache()

    if _cache_is_fresh(cache, pool) and pool in cache:
        log.info("[cache] Loaded %d %s players from cache.", len(cache[pool]), pool)
        return cache[pool]

    from nba_api.stats.endpoints import playerindex

    if pool == "active":
        # active_nullable=1 returns all rostered players regardless of whether they've
        # logged stats yet this season (injured, two-way, etc.) — gives ~539 vs ~135
        # with the default stats-only filter.
        seasons = [("2025-26", {"active_nullable": 1})]
    else:
        # historical_nullable=1 returns all players across all eras in one call.
        seasons = [("2024-25", {"historical_nullable": 1})]

    log.info("[fetch] Fetching PlayerIndex for %s pool via %d bulk request(s) ...", pool, len(seasons))

    seen_ids: set[int] = set()
    enriched: list[dict] = []

    for season, extra_params in seasons:
        try:
            time.sleep(1.0)
            idx = _nba_request_with_retry(
                playerindex.PlayerIndex, season=season, timeout=30, **extra_params
            )
            data = idx.player_index.get_dict()
            headers = data["headers"]
            rows = data["data"]
            h = {name: i for i, name in enumerate(headers)}

            before = len(enriched)
            for row in rows:
                pid = row[h["PERSON_ID"]]
                if pid in seen_ids:
                    continue
                seen_ids.add(pid)
                first = row[h["PLAYER_FIRST_NAME"]] or ""
                last = row[h["PLAYER_LAST_NAME"]] or ""
                name = f"{first} {last}".strip()
                if not name:
                    continue
                team_abbr = row[h.get("TEAM_ABBREVIATION", -1)] if "TEAM_ABBREVIATION" in h else ""
                enriched.append({
                    "id": pid,
                    "name": name,
                    "teams": [team_abbr] if team_abbr else [],
                    "college": str(row[h["COLLEGE"]] or "") if "COLLEGE" in h else "",
                    "draft_year": str(row[h["DRAFT_YEAR"]] or "") if "DRAFT_YEAR" in h else "",
                    "draft_round": str(row[h["DRAFT_ROUND"]] or "") if "DRAFT_ROUND" in h else "",
                    "draft_pick": str(row[h["DRAFT_NUMBER"]] or "") if "DRAFT_NUMBER" in h else "",
                    "jersey": str(row[h["JERSEY_NUMBER"]] or "") if "JERSEY_NUMBER" in h else "",
                    "position": str(row[h["POSITION"]] or "") if "POSITION" in h else "",
                    "country": str(row[h["COUNTRY"]] or "") if "COUNTRY" in h else "",
                    "from_year": str(row[h["FROM_YEAR"]] or "") if "FROM_YEAR" in h else "",
                    "to_year": str(row[h["TO_YEAR"]] or "") if "TO_YEAR" in h else "",
                })
            log.info("[fetch] Season %s: +%d players (total: %d)", season, len(enriched) - before, len(enriched))
        except Exception as exc:
            log.warning("[fetch] Failed to fetch PlayerIndex for season %s: %s", season, exc)
            continue

    if not enriched:
        raise RuntimeError(
            "Failed to fetch any player data from stats.nba.com — check your network connection."
        )

    log.info("[fetch] Fetched %d players total. Saving to cache.", len(enriched))
    cache[pool] = enriched
    cache[f"{pool}_fetched_at"] = datetime.now().isoformat()
    save_cache(cache)
    return enriched


def enrich_with_career_teams(players: list[dict]) -> list[dict]:
    """
    Fetch full career team history for a small set of players (the 16 selected for the puzzle).
    Replaces the single current-team entry from PlayerIndex with a full ordered team list.
    Only ~16 API calls — well within stats.nba.com limits.

    'TOT' is filtered out: it is a stats.nba.com placeholder meaning league-wide total
    for a season in which a player was traded, not a real team.
    """
    from nba_api.stats.endpoints import playercareerstats

    log.info("[enrich] Fetching career team history for %d players ...", len(players))
    for player in players:
        try:
            time.sleep(0.8)
            career = _nba_request_with_retry(
                playercareerstats.PlayerCareerStats, player_id=player["id"], timeout=15
            )
            season_rows = career.season_totals_regular_season.get_dict()
            teams = []
            if season_rows["data"]:
                sh = season_rows["headers"]
                team_idx = sh.index("TEAM_ABBREVIATION")
                seen: set[str] = set()
                for sr in season_rows["data"]:
                    abbr = sr[team_idx]
                    # TOT = stats aggregate row for a traded player; not a real team
                    if abbr and abbr != "TOT" and abbr not in seen:
                        seen.add(abbr)
                        teams.append(abbr)
            if teams:
                player["teams"] = teams
            log.info("[enrich] %-25s teams: %s", player["name"], player["teams"])
        except Exception as exc:
            log.warning("[enrich] Could not fetch career teams for %s: %s", player["name"], exc)
    return players


def select_puzzle_players(pool: str = "active", n: int = 16) -> list[dict]:
    """
    Pick n players ensuring diversity across attribute types so Gemini has enough
    non-team metadata to create varied category connections.

    Strategy: fill the n slots from 4 buckets in rotation —
      - college  (has a college listed)
      - country  (non-USA country)
      - draft    (has draft year + pick number)
      - jersey   (has a jersey number)
    Any remaining slots are filled from the general pool.
    Players are then enriched with full career team history.
    """
    all_players = fetch_players_with_metadata(pool)

    # Strip TOT from PlayerIndex team entries as well (belt-and-suspenders)
    for p in all_players:
        p["teams"] = [t for t in p["teams"] if t and t != "TOT"]

    candidates = [
        p for p in all_players
        if p["name"] and (p["teams"] or p["college"] or p["draft_year"] or p["jersey"])
    ]

    if len(candidates) < n:
        raise ValueError(
            f"Not enough players with metadata to build a puzzle (found {len(candidates)}, need {n})"
        )

    # Build attribute buckets
    bucket_college = [p for p in candidates if p["college"]]
    bucket_country = [p for p in candidates if p["country"] and p["country"] not in ("", "USA")]
    bucket_draft   = [p for p in candidates if p["draft_year"] and p["draft_pick"]]
    bucket_jersey  = [p for p in candidates if p["jersey"]]

    chosen: list[dict] = []
    chosen_ids: set[int] = set()

    def pick_from(bucket: list[dict], k: int) -> list[dict]:
        """Randomly pick up to k players from bucket that aren't already chosen."""
        available = [p for p in bucket if p["id"] not in chosen_ids]
        picks = random.sample(available, min(k, len(available)))
        return picks

    # Fill 3 slots from each diverse bucket (12 total from 4 buckets)
    for bucket in (bucket_college, bucket_country, bucket_draft, bucket_jersey):
        picks = pick_from(bucket, 3)
        for p in picks:
            chosen.append(p)
            chosen_ids.add(p["id"])

    # Fill remaining slots from the general pool
    if len(chosen) < n:
        remaining = pick_from(candidates, n - len(chosen))
        for p in remaining:
            chosen.append(p)
            chosen_ids.add(p["id"])

    # Trim to exactly n (bucket overlaps may push slightly over)
    chosen = chosen[:n]

    # Shuffle so bucket groupings don't leak ordering to Gemini
    random.shuffle(chosen)

    log.info("[select] Selected %d players: %s", len(chosen), ", ".join(p["name"] for p in chosen))
    log.info("[select] Attribute spread — college: %d | non-USA: %d | drafted: %d | jersey: %d",
             sum(1 for p in chosen if p["college"]),
             sum(1 for p in chosen if p["country"] not in ("", "USA")),
             sum(1 for p in chosen if p["draft_year"] and p["draft_pick"]),
             sum(1 for p in chosen if p["jersey"]),
    )

    # Enrich only the 16 chosen players with full career team history (~16 API calls)
    chosen = enrich_with_career_teams(chosen)
    return chosen


# ─────────────────────────────────────────────────────────────────────────────
# Gemini puzzle generation
# ─────────────────────────────────────────────────────────────────────────────

def build_prompt(players: list[dict]) -> str:
    lines = []
    for p in players:
        parts = [f"- {p['name']}"]
        if p["teams"]:
            parts.append(f"teams: {', '.join(p['teams'])}")
        if p["college"]:
            parts.append(f"college: {p['college']}")
        if p["draft_year"] and p["draft_year"] != "Undrafted":
            pick_str = f"{p['draft_year']} draft"
            if p["draft_pick"]:
                pick_str += f" pick #{p['draft_pick']}"
            parts.append(pick_str)
        if p["jersey"]:
            parts.append(f"jersey #{p['jersey']}")
        if p["position"]:
            parts.append(f"position: {p['position']}")
        if p["country"] and p["country"] != "USA":
            parts.append(f"country: {p['country']}")
        lines.append(" | ".join(parts))

    player_block = "\n".join(lines)

    return f"""You are designing an NBA-themed Connections puzzle (like the NYT Connections game).

Here are 16 NBA players with their real career metadata:

{player_block}

Your task: organise ALL 16 players into exactly 4 groups of 4.

CRITICAL DIVERSITY RULE: You MUST use AT MOST 2 team-based connections across all 4 groups.
The other 2 groups MUST be based on non-team attributes such as:
  - Same college / university
  - Same draft year or draft class
  - Same jersey number
  - Same country of origin (non-USA)
  - Same position
  - Same draft round or pick range
  - Any other non-team connection supported by the metadata

Each group must share one hidden connection that is:
- Factually accurate based ONLY on the metadata provided above — do NOT invent facts
- Specific (e.g. "PLAYED AT DUKE" not just "SAME COLLEGE", "WORE #23" not just "SAME JERSEY")
- Progressively harder: difficulty 1 is the most obvious, difficulty 4 is the most surprising
- At least one group should be a red herring — players that look like they belong elsewhere

Rules:
- Every player appears in exactly one group
- No more than 2 of the 4 groups may be team-based connections
- Category names are SHORT, UPPERCASE, and punchy (2–6 words)
- Difficulty levels 1, 2, 3, and 4 must each be used exactly once

Return your answer as structured JSON."""


def generate_puzzle(players: list[dict]) -> PuzzleResponse:
    """Call Gemini to create puzzle groups and validate the response."""
    client = get_gemini_client()
    prompt = build_prompt(players)

    log.info("[gemini] Sending %d players to gemini-2.5-flash for puzzle generation ...", len(players))
    t0 = time.time()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_json_schema": PuzzleResponse.model_json_schema(),
        },
    )
    log.info("[gemini] Response received in %.1fs. Validating ...", time.time() - t0)

    puzzle = PuzzleResponse.model_validate_json(response.text)

    # --- Semantic validation ---
    player_names = {p["name"] for p in players}
    used: set[str] = set()
    difficulties: set[int] = set()

    for group in puzzle.groups:
        if len(group.players) != 4:
            raise ValueError(f"Group '{group.category}' has {len(group.players)} players, expected 4")
        for pname in group.players:
            # Allow minor name variations by checking case-insensitively
            matched = next(
                (n for n in player_names if n.lower() == pname.lower()), None
            )
            if matched is None:
                raise ValueError(f"Player '{pname}' not in the provided player list")
            if matched in used:
                raise ValueError(f"Player '{matched}' appears in more than one group")
            used.add(matched)
        difficulties.add(group.difficulty)

    if len(used) != 16:
        raise ValueError(f"Puzzle uses {len(used)} players, expected 16")
    if difficulties != {1, 2, 3, 4}:
        raise ValueError(f"Difficulty levels used: {difficulties}, expected {{1,2,3,4}}")

    log.info("[gemini] Puzzle validated OK. Groups:")
    for g in sorted(puzzle.groups, key=lambda x: x.difficulty):
        log.info("  [%d] %s -> %s", g.difficulty, g.category, ", ".join(g.players))

    return puzzle


# ─────────────────────────────────────────────────────────────────────────────
# Flask routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """
    Request body (JSON): { "player_pool": "active" | "all_time" }
    Response: { "puzzle_id": "...", "players": ["Name1", ...16 shuffled names...] }
    """
    data = request.get_json(silent=True) or {}
    pool = data.get("player_pool", "active")
    if pool not in ("active", "all_time"):
        return jsonify({"error": "player_pool must be 'active' or 'all_time'"}), 400

    # Validate API key early — before making expensive nba_api network calls
    try:
        get_gemini_client()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    log.info("[api] POST /api/generate | pool=%s", pool)
    t_start = time.time()
    try:
        players = select_puzzle_players(pool)
        puzzle_resp = generate_puzzle(players)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except ValueError as e:
        return jsonify({"error": f"Puzzle generation failed: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {e}"}), 500

    puzzle_id = str(uuid.uuid4())

    # Build normalised group map (lowercase name → group index)
    groups_data = []
    for group in sorted(puzzle_resp.groups, key=lambda g: g.difficulty):
        groups_data.append({
            "category": group.category,
            "players": group.players,  # canonical names as Gemini returned them
            "difficulty": group.difficulty,
            "color": DIFFICULTY_COLORS[group.difficulty],
            "hex": DIFFICULTY_HEX[group.difficulty],
            "explanation": group.connection_explanation,
        })

    log.info("[api] Puzzle ready (id=%s) in %.1fs total.", puzzle_id, time.time() - t_start)

    # Build name → group_index lookup (lowercase for tolerance)
    name_to_group: dict[str, int] = {}
    for idx, g in enumerate(groups_data):
        for pname in g["players"]:
            name_to_group[pname.lower()] = idx

    _puzzles[puzzle_id] = {
        "groups": groups_data,
        "name_to_group": name_to_group,
        "solved": [],   # list of group indices already solved
        "created_at": datetime.now().isoformat(),
    }

    # Return shuffled player list (names only) — answers stay server-side
    all_names = [p for g in groups_data for p in g["players"]]
    random.shuffle(all_names)

    return jsonify({"puzzle_id": puzzle_id, "players": all_names})


@app.route("/api/validate", methods=["POST"])
def api_validate():
    """
    Request body (JSON):
        { "puzzle_id": "...", "selected": ["Name1", "Name2", "Name3", "Name4"] }
    Response (correct):
        { "correct": true, "group": { "category": "...", "color": "...", "hex": "...",
          "difficulty": 1, "explanation": "...", "players": [...] } }
    Response (incorrect):
        { "correct": false, "one_away": true|false }
    Response (already solved):
        { "error": "already_solved" }
    """
    data = request.get_json(silent=True) or {}
    puzzle_id = data.get("puzzle_id", "")
    selected: list[str] = data.get("selected", [])

    if puzzle_id not in _puzzles:
        return jsonify({"error": "Puzzle not found or expired"}), 404

    puzzle = _puzzles[puzzle_id]

    if len(selected) != 4:
        return jsonify({"error": "Must select exactly 4 players"}), 400

    # Enforce that all 4 selections are distinct (case-insensitive)
    normalized_selected = [str(name).lower() for name in selected]
    if len(set(normalized_selected)) != len(normalized_selected):
        return jsonify({"error": "Must select 4 distinct players"}), 400
    # Determine which group each selected player belongs to
    group_indices = []
    for name in selected:
        g_idx = puzzle["name_to_group"].get(name.lower())
        if g_idx is None:
            return jsonify({"error": f"Unknown player: {name}"}), 400
        group_indices.append(g_idx)

    # Check if already solved
    target_group = group_indices[0]
    if target_group in puzzle["solved"]:
        return jsonify({"error": "already_solved"}), 400

    correct = all(g == target_group for g in group_indices)

    if correct:
        puzzle["solved"].append(target_group)
        group = puzzle["groups"][target_group]
        return jsonify({
            "correct": True,
            "group": {
                "category": group["category"],
                "color": group["color"],
                "hex": group["hex"],
                "difficulty": group["difficulty"],
                "explanation": group["explanation"],
                "players": group["players"],
            },
        })
    else:
        # "One away" hint: exactly 3 of 4 are in the same group
        from collections import Counter
        counts = Counter(group_indices)
        one_away = max(counts.values()) == 3
        return jsonify({"correct": False, "one_away": one_away})


@app.route("/api/reveal", methods=["POST"])
def api_reveal():
    """
    Called at game over to reveal all remaining unsolved groups.
    Request body: { "puzzle_id": "..." }
    Response: { "remaining_groups": [ { group data ... }, ... ] }
    """
    data = request.get_json(silent=True) or {}
    puzzle_id = data.get("puzzle_id", "")

    if puzzle_id not in _puzzles:
        return jsonify({"error": "Puzzle not found"}), 404

    puzzle = _puzzles[puzzle_id]
    remaining = [
        {
            "category": g["category"],
            "color": g["color"],
            "hex": g["hex"],
            "difficulty": g["difficulty"],
            "explanation": g["explanation"],
            "players": g["players"],
        }
        for idx, g in enumerate(puzzle["groups"])
        if idx not in puzzle["solved"]
    ]

    return jsonify({"remaining_groups": remaining})


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse as _argparse

    _parser = _argparse.ArgumentParser(add_help=False)
    _parser.add_argument("--host", default="127.0.0.1")
    _parser.add_argument("--port", type=int, default=5000)
    _args, _ = _parser.parse_known_args()

    app.run(debug=True, host=_args.host, port=_args.port)
