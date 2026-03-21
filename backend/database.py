"""
Supabase integration — two-level cache:

Level 1: game_analysis  (keyed by game_id, permanent, stores Stockfish results)
Level 2: analyses       (keyed by games_hash, TTL 1hr, stores full Claude output)
"""
import hashlib
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from supabase import create_client, Client

CACHE_TTL_HOURS = 24


def _get_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    return create_client(url, key)


# ── Helpers ───────────────────────────────────────────────────────────────────

def compute_games_hash(game_ids: list[str]) -> str:
    """Stable hash of a set of game IDs — order-independent."""
    key = ",".join(sorted(game_ids))
    return hashlib.sha256(key.encode()).hexdigest()


# ── Level 1: Per-game Stockfish cache ─────────────────────────────────────────

def get_game_analyses_batch(game_ids: list[str]) -> dict[str, dict]:
    """
    Fetch cached Stockfish results for a batch of game IDs.
    Returns dict mapping game_id -> {acpl, key_positions}.
    """
    if not game_ids:
        return {}
    try:
        client = _get_client()
        resp = (
            client.table("game_analysis")
            .select("game_id, acpl, key_positions")
            .in_("game_id", game_ids)
            .execute()
        )
        return {row["game_id"]: row for row in (resp.data or [])}
    except Exception:
        return {}


def save_game_analyses_batch(analyses: list[dict]) -> None:
    """
    Upsert per-game Stockfish results.
    Each item: {game_id, acpl, key_positions (list of dicts)}.
    """
    if not analyses:
        return
    try:
        client = _get_client()
        client.table("game_analysis").upsert(analyses, on_conflict="game_id").execute()
    except Exception:
        pass


# ── Level 2: Query-level Claude output cache ──────────────────────────────────

def get_cached_analysis(games_hash: str) -> Optional[dict]:
    """
    Return cached full analysis if it exists and is fresher than CACHE_TTL_HOURS.
    """
    try:
        client = _get_client()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=CACHE_TTL_HOURS)).isoformat()
        resp = (
            client.table("analyses")
            .select("result, created_at")
            .eq("games_hash", games_hash)
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]["result"]
        return None
    except Exception:
        return None


def save_analysis(
    username: str,
    months: int,
    speed: str,
    games_hash: str,
    result: dict,
) -> Optional[str]:
    """Save full analysis result + per-opening stats."""
    try:
        client = _get_client()
        resp = (
            client.table("analyses")
            .insert({
                "username": username.lower(),
                "months": months,
                "speed": speed,
                "games_hash": games_hash,
                "result": result,
                "user_rating": result.get("user_rating"),
                "total_games": result.get("total_games"),
            })
            .execute()
        )
        if not resp.data:
            return None

        analysis_id = resp.data[0]["id"]

        rows = []
        for color in ("white", "black"):
            for opening in result.get(f"{color}_openings", []):
                stats = opening.get("stats", {})
                rows.append({
                    "username": username.lower(),
                    "analysis_id": analysis_id,
                    "color": color,
                    "opening_name": stats.get("name", ""),
                    "eco": stats.get("eco", ""),
                    "games": stats.get("games", 0),
                    "wins": stats.get("wins", 0),
                    "draws": stats.get("draws", 0),
                    "losses": stats.get("losses", 0),
                    "avg_opponent_rating": stats.get("avg_opponent_rating"),
                    "avg_centipawn_loss": opening.get("avg_centipawn_loss"),
                    "verdict": opening.get("verdict"),
                })
        if rows:
            client.table("opening_stats").insert(rows).execute()

        return analysis_id
    except Exception:
        return None


# ── History & Trends ──────────────────────────────────────────────────────────

def get_analysis_history(username: str, limit: int = 10) -> list[dict]:
    try:
        client = _get_client()
        resp = (
            client.table("analyses")
            .select("id, months, speed, user_rating, total_games, created_at")
            .eq("username", username.lower())
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return resp.data or []
    except Exception:
        return []


def get_opening_trends(username: str, opening_name: str, color: str) -> list[dict]:
    try:
        client = _get_client()
        resp = (
            client.table("opening_stats")
            .select("games, wins, draws, losses, avg_centipawn_loss, verdict, created_at")
            .eq("username", username.lower())
            .eq("opening_name", opening_name)
            .eq("color", color)
            .order("created_at", desc=False)
            .limit(20)
            .execute()
        )
        rows = resp.data or []
        for row in rows:
            total = row["games"] or 1
            row["win_rate"] = round(row["wins"] / total * 100)
            row["date_label"] = row["created_at"][:10]
        return rows
    except Exception:
        return []
