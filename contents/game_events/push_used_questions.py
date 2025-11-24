"""
Push Used Questions Snapshot to GitHub

This helper provides a single function to serialize the questions that were
used during a game session and push them to the configured GitHub repository.
It is designed to be called when the host clicks "End Game" so that a record
of the used questions is stored online for auditing or sharing.

Minimal external dependencies: relies on existing AdminSetup settings and the
GitHubIntegration class already used by the admin push tool.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Set

from contents.admin_controls.github_integration import GitHubIntegration
from questionmanagement.question_bank import question_bank


def _collect_used_question_ids(game_room) -> Set[str]:
    """Collect the set of used/answered question IDs from a game room.

    Tries multiple attributes for robustness across game types.
    """
    used: Set[str] = set()

    # Most boards track answered questions in a set
    answered = getattr(game_room, "answered_questions", None)
    if isinstance(answered, set):
        used |= answered
    # Hive game uses answered_question_ids
    answered_hive = getattr(game_room, "answered_question_ids", None)
    if isinstance(answered_hive, set):
        used |= answered_hive

    # Some engines might track a history list
    history = getattr(game_room, "question_history", None)
    if isinstance(history, list):
        for item in history:
            if isinstance(item, dict) and item.get("id"):
                used.add(item["id"])

    # As a final fallback, scan the board for answered flags if present
    board = getattr(game_room, "board", None)
    if isinstance(board, dict):
        try:
            for _cat, points_dict in board.items():
                for _points, q_list in points_dict.items():
                    for q in q_list:
                        # If questions are marked answered in place somehow
                        if isinstance(q, dict):
                            if q.get("answered") is True and q.get("id"):
                                used.add(q["id"])
        except Exception:
            # Keep best-effort
            pass

    # If the current question exists and was revealed/answered, include it
    cq = getattr(game_room, "current_question", None)
    if isinstance(cq, dict) and cq.get("id"):
        # Only include if the room marked it answered already
        if cq.get("id") in used or getattr(game_room, "answer_revealed", False):
            used.add(cq["id"])

    return used


def _resolve_questions(question_ids: Set[str]) -> List[Dict[str, Any]]:
    """Resolve question IDs to full question objects from the question bank.

    Returns only fields likely useful downstream to keep snapshot concise.
    """
    try:
        # Ensure latest view
        question_bank.load_questions()
    except Exception:
        pass

    out: List[Dict[str, Any]] = []
    for qid in sorted(question_ids):
        q = question_bank.questions.get(qid) if hasattr(question_bank, "questions") else None
        if isinstance(q, dict):
            # Make a shallow copy and keep key fields
            filtered = {
                "id": q.get("id", qid),
                "type": q.get("type"),
                "category_id": q.get("category_id"),
                "question": q.get("question"),
                "options": q.get("options"),
                "correct_answer": q.get("correct_answer"),
                "points": q.get("points"),
                "source_file": q.get("source_file"),
                "use_count": q.get("use_count"),
            }
            out.append(filtered)
        else:
            out.append({"id": qid})
    return out


def push_used_questions_snapshot(game_room, admin_setup, mode: str = "fastest") -> (bool, str):
    """Push a JSON snapshot of used questions for the given game room to GitHub.

    Args:
        game_room: The in-memory game room object (has room_id, name, host, players, etc.).
        admin_setup: AdminSetup instance with GitHub settings in game_settings.
        mode (str): Game mode identifier for path scoping (e.g., "fastest", "columns").

    Returns:
        tuple(bool, str): success flag and message
    """
    try:
        # Gather metadata
        utc_now = datetime.now(timezone.utc)
        timestamp = utc_now.strftime("%Y%m%dT%H%M%SZ")

        players = list(getattr(game_room, "players", []))
        host = getattr(game_room, "host", None)
        room_name = getattr(game_room, "name", None)
        room_id = getattr(game_room, "room_id", None)

        # Leaderboard or scores if available
        leaderboard = None
        if hasattr(game_room, "get_leaderboard"):
            try:
                leaderboard = game_room.get_leaderboard()
            except Exception:
                leaderboard = None
        if leaderboard is None and hasattr(game_room, "player_scores"):
            try:
                leaderboard = sorted(getattr(game_room, "player_scores", {}).items(), key=lambda x: x[1], reverse=True)
            except Exception:
                leaderboard = None

        used_ids = _collect_used_question_ids(game_room)
        questions = _resolve_questions(used_ids)

        snapshot = {
            "schema": "avirta.game_run.v1",
            "created_utc": timestamp,
            "game_mode": mode,
            "room": {
                "id": room_id,
                "name": room_name,
                "host": host,
                "players": players,
            },
            "stats": {
                "total_questions": getattr(game_room, "total_questions", None),
                "answered_count": len(used_ids),
                "current_question_number": getattr(game_room, "current_question_number", None),
            },
            "leaderboard": leaderboard,
            "questions": questions,
        }

        content = json.dumps(snapshot, ensure_ascii=False, indent=2)

        # GitHub settings
        github_token = admin_setup.game_settings.get("github_token", "")
        github_repo_owner = admin_setup.game_settings.get("github_repo_owner", "")
        github_repo_name = admin_setup.game_settings.get("github_repo_name", "")
        github_branch = admin_setup.game_settings.get("github_branch", "main")

        if not github_token or not github_repo_owner or not github_repo_name:
            return False, "GitHub settings are incomplete; skipping push of used questions."

        github = GitHubIntegration(github_token, github_repo_owner, github_repo_name, github_branch)

        # File path on GitHub repository
        safe_mode = (mode or "game").lower().strip()
        filename = f"{room_id or 'room'}-{timestamp}.json"
        github_path = f"game_runs/{safe_mode}/{filename}"

        commit_message = f"Add game run snapshot for room {room_id} ({safe_mode}) at {timestamp}"
        success, message = github.push_file_to_github(github_path, content, commit_message)
        return success, message

    except Exception as e:
        return False, f"Error pushing used questions snapshot: {e}" 
