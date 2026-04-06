"""
NBA Connections — Flask Routes
"""

import logging
import random
import time
import uuid
from collections import Counter
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request

from engine import (
    DIFFICULTY_COLORS,
    DIFFICULTY_HEX,
    _puzzles,
    generate_puzzle,
    get_gemini_client,
)
from players import select_puzzle_players

log = logging.getLogger(__name__)

blueprint = Blueprint("nba_connections", __name__)


@blueprint.route("/")
def index():
    return render_template("index.html")


@blueprint.route("/api/generate", methods=["POST"])
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


@blueprint.route("/api/validate", methods=["POST"])
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
        counts = Counter(group_indices)
        one_away = max(counts.values()) == 3
        return jsonify({"correct": False, "one_away": one_away})


@blueprint.route("/api/reveal", methods=["POST"])
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
