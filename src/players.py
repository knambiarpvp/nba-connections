"""
NBA Connections — Player Data
Cache helpers, NBA API fetching, and puzzle player selection.
"""

import json
import logging
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Path helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_writable_path() -> Path:
    """Writable directory: next to the .exe when frozen, else next to this file."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


WRITABLE_PATH = _get_writable_path()


# ─────────────────────────────────────────────────────────────────────────────
# Player data cache
# ─────────────────────────────────────────────────────────────────────────────

CACHE_FILE = WRITABLE_PATH / "cache" / "players_cache.json"
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
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
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


# ─────────────────────────────────────────────────────────────────────────────
# Player data fetching
# ─────────────────────────────────────────────────────────────────────────────

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
                h_map = {col: i for i, col in enumerate(sh)}
                team_idx = h_map["TEAM_ABBREVIATION"]
                # For career-stats totals, prefer TOT rows (traded seasons) to avoid
                # double-counting; fall back to the single non-TOT row otherwise.
                season_pts: dict[str, int] = {}  # season_id → pts (deduplicated)
                season_gp: dict[str, int] = {}
                seen: set[str] = set()
                for sr in season_rows["data"]:
                    abbr = sr[team_idx]
                    # Teams list: skip TOT placeholder
                    if abbr and abbr != "TOT" and abbr not in seen:
                        seen.add(abbr)
                        teams.append(abbr)
                    # Career stats: use TOT rows when present to avoid double-counting
                    sid = sr[h_map["SEASON_ID"]] if "SEASON_ID" in h_map else None
                    if sid is not None:
                        pts = int(sr[h_map["PTS"]] or 0) if "PTS" in h_map else 0
                        gp = int(sr[h_map["GP"]] or 0) if "GP" in h_map else 0
                        if abbr == "TOT" or sid not in season_pts:
                            season_pts[sid] = pts
                            season_gp[sid] = gp
                player["career_pts"] = sum(season_pts.values())
                player["career_gp"] = sum(season_gp.values())
            else:
                player["career_pts"] = 0
                player["career_gp"] = 0
            if teams:
                player["teams"] = teams
            log.info("[enrich] %-25s teams: %s | career: %d pts in %d gp",
                     player["name"], player["teams"],
                     player.get("career_pts", 0), player.get("career_gp", 0))
        except Exception as exc:
            log.warning("[enrich] Could not fetch career teams for %s: %s", player["name"], exc)
    return players


def _pre_enrich_fame(player: dict) -> float:
    """
    Heuristic recognizability score using only PlayerIndex fields (no career-stats call
    needed). Used to bias player selection toward household names before enrichment.
    """
    score = 1.0  # floor so every player has a positive weight
    # Career length: more seasons → more name recognition
    try:
        fy = int(player.get("from_year") or 0)
        ty = int(player.get("to_year") or 0)
        if fy and ty:
            score += (ty - fy) * 3.0
    except (ValueError, TypeError):
        pass
    # Lottery pick: top-15 picks are usually franchise cornerstones
    try:
        pick = int(player.get("draft_pick") or 0)
        if 0 < pick <= 5:
            score += 25.0
        elif pick <= 10:
            score += 15.0
        elif pick <= 15:
            score += 8.0
        elif pick <= 20:
            score += 4.0
    except (ValueError, TypeError):
        pass
    return score


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

    # Seed the pool with a variable number of high-recognizability players so
    # every puzzle contains well-known names without always showing the same faces.
    fame_sorted = sorted(candidates, key=_pre_enrich_fame, reverse=True)
    top_tier_size = random.randint(30, min(50, len(fame_sorted)))
    top_tier = fame_sorted[:top_tier_size]
    star_count = random.randint(3, min(9, len(top_tier)))
    stars = random.sample(top_tier, star_count)
    for p in stars:
        chosen.append(p)
        chosen_ids.add(p["id"])

    def pick_from(bucket: list[dict], k: int) -> list[dict]:
        """Fame-weighted pick of up to k players from bucket that aren't already chosen."""
        available = [p for p in bucket if p["id"] not in chosen_ids]
        k = min(k, len(available))
        if k == 0:
            return []
        # Weighted sampling without replacement — higher fame score = more likely picked
        weights = [_pre_enrich_fame(p) for p in available]
        pool_pairs = list(zip(available, weights))
        picks: list[dict] = []
        for _ in range(k):
            total = sum(w for _, w in pool_pairs)
            r = random.uniform(0, total)
            cumulative = 0.0
            for i, (player, w) in enumerate(pool_pairs):
                cumulative += w
                if r <= cumulative:
                    picks.append(player)
                    pool_pairs.pop(i)
                    break
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
