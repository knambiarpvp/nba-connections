"""
NBA Connections — Game Engine
Pydantic schemas, puzzle store, Gemini prompt/generation, and uniqueness validation.
"""

import logging
import os
import time
from datetime import datetime, timedelta

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Gemini client
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
    connection_attribute: str = Field(
        description=(
            "The exact player metadata field that defines this group's connection. "
            "Must be one of: 'teams', 'college', 'draft_year', 'draft_round', 'draft_pick', 'jersey', 'position', 'country'"
        )
    )
    connection_value: str = Field(
        description=(
            "The minimum (or only) exact value of connection_attribute shared by all 4 players. "
            "For exact connections: 'LAL' for teams, 'Duke' for college, '2003' for draft_year, "
            "'23' for jersey, 'F' for position, 'Canada' for country. "
            "For range-based numeric connections (draft_pick, draft_year), set this to the lower bound "
            "and set connection_value_max to the upper bound."
        )
    )
    connection_value_max: str = Field(
        default="",
        description=(
            "Upper bound for range-based numeric connections only (draft_pick or draft_year). "
            "Leave empty for exact-match connections. "
            "Example: 'Top 4 draft picks' → connection_attribute='draft_pick', connection_value='1', connection_value_max='4'. "
            "'Lottery picks (1-14)' → connection_value='1', connection_value_max='14'."
        )
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
DIFFICULTY_COLORS = {1: "yellow", 2: "green", 3: "blue", 4: "purple"}
DIFFICULTY_HEX = {1: "#f9df6d", 2: "#a0c35a", 3: "#b0c4ef", 4: "#ba81c5"}


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
        if p.get("career_pts"):
            parts.append(f"career pts: {p['career_pts']}")
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
- Progressively harder: difficulty 1 has the most obvious connection and should feel immediately recognisable to a casual fan; difficulty 4 is the most surprising
- Well-known players (high career pts) may appear in any group, but the difficulty 1 group as a whole should be the most guessable connection — not necessarily the most famous individuals, but the most intuitive shared trait
- At least one group should be a red herring — players that look like they belong elsewhere

Rules:
- Every player appears in exactly one group
- No more than 2 of the 4 groups may be team-based connections
- Team-based groups MUST name a specific team abbreviation (e.g. 'PLAYED FOR LAL'), NEVER a conference or region ('WESTERN CONFERENCE TEAMS' is INVALID)
- Category names are SHORT, UPPERCASE, and punchy (2–6 words)
- Difficulty levels 1, 2, 3, and 4 must each be used exactly once
- Each group's connection MUST be a single, exact shared value — NEVER use "or" conditions
  ("WORE #2 OR #5" is INVALID; "WORE #23" is VALID. "DRAFTED IN 2020" is VALID; "DRAFTED IN 2019 OR 2020" is INVALID)
- Position groups must use a single exact position code (e.g. 'G-F'), never a combination
- Difficulty 3 and 4 groups may include role players that only hardcore fans would recognise

CRITICAL — UNIQUENESS CHECK: Before finalising, cross-check every group: verify that NONE of the 12 players outside that group also satisfy that group's connection. If even one outsider qualifies, the group is ambiguous — replace it with a tighter connection. A puzzle with interchangeable players is invalid.

For each group set connection_attribute to the metadata field name (one of: 'teams', 'college', 'draft_year', 'draft_round', 'draft_pick', 'jersey', 'position', 'country') and connection_value to the exact shared value or range lower bound.
  - For exact connections (teams, college, jersey, draft_year, draft_round, country): set connection_value to the precise value and leave connection_value_max empty.
  - For range-based numeric connections (draft_pick, draft_year): set connection_value to the lowest qualifying number and connection_value_max to the highest (e.g. 'Top 4 draft picks' → connection_value='1', connection_value_max='4').
  - For country groups where all 4 players share the same country, use that country name as connection_value.
  - For country groups where the shared trait is being born outside the USA (players from different countries), use 'Non-USA' as connection_value.
  - For position groups, use a single position letter (e.g. 'F', 'G', 'C') — a player with position 'F-C' satisfies both 'F' and 'C'.

Return your answer as structured JSON."""


_MAX_GENERATE_ATTEMPTS = 3

_VALID_CONNECTION_ATTRIBUTES = frozenset(
    {"teams", "college", "draft_year", "draft_round", "draft_pick", "jersey", "position", "country"}
)


def _validate_uniqueness(puzzle: PuzzleResponse, players: list[dict]) -> list[str]:
    """
    Check that no two players from different groups are mutually interchangeable —
    i.e., swapping them would produce an equally valid complete solution.

    A player satisfying another group's connection in isolation is fine (that's a red
    herring). We only flag cases where player A (group X) satisfies group Y's connection
    AND player B (group Y) simultaneously satisfies group X's connection.

    Groups whose connection_attribute is missing, unrecognised, or seems hallucinated
    (e.g. connection_value='S' for a 'teams' attribute) are silently skipped — Gemini
    sometimes uses compound connections that don't map to a single metadata field.
    """
    name_to_player = {p["name"].lower(): p for p in players}
    violations: list[str] = []

    def _matches(p: dict, attr: str, val: str, val_max: str = "") -> bool:
        if attr == "teams":
            return val in (p.get("teams") or [])
        if attr == "country":
            if val.lower() in ("non-usa", "international"):
                return p.get("country", "") not in ("", "USA")
            return (str(p.get("country") or "")).strip().lower() == val.lower()
        if attr == "position":
            raw = str(p.get("position") or "")
            parts = [pt.strip().upper() for pt in raw.split("-") if pt.strip()]
            return val.upper() in parts or raw.upper() == val.upper()
        if val_max:
            try:
                raw_int = int(str(p.get(attr) or ""))
                return int(val) <= raw_int <= int(val_max)
            except (ValueError, TypeError):
                return False
        return (str(p.get(attr) or "")).strip().lower() == val.lower()

    def _group_is_checkable(attr: str, val: str, val_max: str, members: set) -> bool:
        """Return True only when the attr/val look reliable enough to swap-check."""
        if not attr or attr not in _VALID_CONNECTION_ATTRIBUTES:
            return False
        if not val:
            return False
        # Sanity-check: at least 3 of the 4 group members must satisfy the declared
        # connection. If fewer do, Gemini likely hallucinated the attr/val (e.g.
        # connection_attribute='teams', connection_value='S' for an international group).
        qualifying = sum(
            1 for n in members
            if name_to_player.get(n) and _matches(name_to_player[n], attr, val, val_max)
        )
        return qualifying >= 3

    # Build per-group metadata
    group_info: list[tuple] = []  # (group, attr, val, val_max, member_set, checkable)
    for group in puzzle.groups:
        attr = (group.connection_attribute or "").strip()
        val = (group.connection_value or "").strip()
        val_max = (group.connection_value_max or "").strip()
        member_lower = {n.lower() for n in group.players}
        checkable = _group_is_checkable(attr, val, val_max, member_lower)
        if not checkable:
            log.debug(
                "[validate] Skipping swap-check for '%s' (attr=%r val=%r) — compound or unverifiable connection",
                group.category, attr, val,
            )
        group_info.append((group, attr, val, val_max, member_lower, checkable))

    # Mutual-swap check across all pairs of checkable groups
    for i, (gx, ax, vx, vmx, mx, cx) in enumerate(group_info):
        if not cx:
            continue
        for j, (gy, ay, vy, vmy, my, cy) in enumerate(group_info):
            if j <= i or not cy:
                continue
            gx_fits_gy = [
                name_to_player[n] for n in mx
                if name_to_player.get(n) and _matches(name_to_player[n], ay, vy, vmy)
            ]
            gy_fits_gx = [
                name_to_player[n] for n in my
                if name_to_player.get(n) and _matches(name_to_player[n], ax, vx, vmx)
            ]
            for pa in gx_fits_gy:
                for pb in gy_fits_gx:
                    violations.append(
                        f"'{pa['name']}' ({gx.category}) and '{pb['name']}' ({gy.category}) "
                        f"are interchangeable: swapping them produces an alternate valid solution"
                    )

    return violations


def generate_puzzle(players: list[dict]) -> PuzzleResponse:
    """Call Gemini to create puzzle groups, validate, and retry up to 3 times on failure."""
    client = get_gemini_client()
    prompt = build_prompt(players)
    player_names = {p["name"] for p in players}

    last_error: Exception | None = None
    for attempt in range(1, _MAX_GENERATE_ATTEMPTS + 1):
        if attempt > 1:
            log.warning("[gemini] Retrying puzzle generation (attempt %d/%d) ...", attempt, _MAX_GENERATE_ATTEMPTS)

        log.info("[gemini] Sending %d players to gemini-2.5-flash (attempt %d) ...", len(players), attempt)
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

        try:
            puzzle = PuzzleResponse.model_validate_json(response.text)

            # --- Structural validation ---
            used: set[str] = set()
            difficulties: set[int] = set()

            for group in puzzle.groups:
                if len(group.players) != 4:
                    raise ValueError(f"Group '{group.category}' has {len(group.players)} players, expected 4")
                for pname in group.players:
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

            # --- Uniqueness validation ---
            violations = _validate_uniqueness(puzzle, players)
            if violations:
                raise ValueError(
                    "Interchangeable players detected:\n" + "\n".join(f"  - {v}" for v in violations)
                )

            log.info("[gemini] Puzzle validated OK. Groups:")
            for g in sorted(puzzle.groups, key=lambda x: x.difficulty):
                log.info("  [%d] %s -> %s", g.difficulty, g.category, ", ".join(g.players))

            return puzzle

        except ValueError as exc:
            log.warning("[gemini] Attempt %d validation failed: %s", attempt, exc)
            last_error = exc

    raise ValueError(
        f"Puzzle generation failed after {_MAX_GENERATE_ATTEMPTS} attempts. Last error: {last_error}"
    )
