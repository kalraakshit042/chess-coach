"""
Supabase integration.

Tables:
  lichess_players   — lightweight player registry
  all_games         — permanent game metadata (one row per Lichess game)
  stockfish_analysis — engine results per game (acpl + key positions, both sides)
  player_games      — join: username ↔ game_id + color played
  analyses          — Claude output cache keyed by games_hash (24hr TTL)
  opening_stats     — per-opening snapshots per analysis run (future trends)
"""
import hashlib
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from supabase import create_client, Client

CACHE_TTL_HOURS = 24

log = logging.getLogger("database")


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


# ── all_games table ───────────────────────────────────────────────────────────

def get_existing_game_ids(game_ids: list[str]) -> set[str]:
    """Return which of the given game_ids already exist in all_games."""
    if not game_ids:
        return set()
    try:
        client = _get_client()
        resp = (
            client.table("all_games")
            .select("game_id")
            .in_("game_id", game_ids)
            .execute()
        )
        found = {row["game_id"] for row in (resp.data or [])}
        log.info(f"[all_games] checked {len(game_ids)} game IDs → {len(found)} already exist")
        return found
    except Exception as e:
        log.error(f"[all_games] get_existing_game_ids failed: {e}")
        return set()


def save_all_games_batch(rows: list[dict]) -> None:
    """Upsert game metadata rows into all_games (no Stockfish data)."""
    if not rows:
        return
    try:
        client = _get_client()
        client.table("all_games").upsert(rows, on_conflict="game_id").execute()
        log.info(f"[all_games] saved {len(rows)} game metadata rows")
    except Exception as e:
        log.error(f"[all_games] save_all_games_batch failed: {e}")


# ── stockfish_analysis table ──────────────────────────────────────────────────

def get_stockfish_analyses(game_ids: list[str]) -> dict[str, dict]:
    """
    Load Stockfish results for a batch of game IDs.
    Returns dict: game_id → {acpl_white, acpl_black, key_positions_white, key_positions_black}
    """
    if not game_ids:
        return {}
    try:
        client = _get_client()
        resp = (
            client.table("stockfish_analysis")
            .select("game_id, acpl_white, acpl_black, key_positions_white, key_positions_black")
            .in_("game_id", game_ids)
            .execute()
        )
        found = {row["game_id"]: row for row in (resp.data or [])}
        log.info(f"[stockfish_analysis] loaded {len(found)} existing analyses")
        return found
    except Exception as e:
        log.error(f"[stockfish_analysis] get_stockfish_analyses failed: {e}")
        return {}


def save_stockfish_analyses(rows: list[dict]) -> None:
    """Upsert Stockfish analysis rows. Each row: {game_id, acpl_white, acpl_black, ...}"""
    if not rows:
        log.info("[stockfish_analysis] nothing new to save")
        return
    try:
        client = _get_client()
        client.table("stockfish_analysis").upsert(rows, on_conflict="game_id").execute()
        log.info(f"[stockfish_analysis] saved {len(rows)} new analysis rows")
    except Exception as e:
        log.error(f"[stockfish_analysis] save_stockfish_analyses failed: {e}")


def get_games_for_opening(username: str, eco: str, opening_name: str, color: str) -> list[dict]:
    """
    Load all game rows for a specific user + opening from all_games via player_games.
    Returns list of all_games rows (with game metadata).
    """
    try:
        client = _get_client()
        # Step 1: get all game_ids for this user + color
        pg_resp = (
            client.table("player_games")
            .select("game_id")
            .eq("username", username.lower())
            .eq("color", color)
            .execute()
        )
        game_ids = [r["game_id"] for r in (pg_resp.data or [])]
        if not game_ids:
            log.info(f"[player_games] no games found for {username}/{color}")
            return []

        # Step 2: filter by eco + opening_name
        ag_resp = (
            client.table("all_games")
            .select("*")
            .in_("game_id", game_ids)
            .eq("eco", eco)
            .eq("opening_name", opening_name)
            .execute()
        )
        rows = ag_resp.data or []
        log.info(f"[all_games] found {len(rows)} games for {username}/{opening_name}/{color}")
        return rows
    except Exception as e:
        log.error(f"[all_games] get_games_for_opening failed: {e}")
        return []


# ── lichess_players table ─────────────────────────────────────────────────────

def upsert_lichess_player(username: str) -> None:
    """Track that we've fetched games for this Lichess username."""
    try:
        client = _get_client()
        client.table("lichess_players").upsert(
            {
                "username": username.lower(),
                "last_fetched_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="username",
        ).execute()
        log.info(f"[lichess_players] upserted: {username.lower()}")
    except Exception as e:
        log.error(f"[lichess_players] upsert_lichess_player failed: {e}")


# ── player_games table ────────────────────────────────────────────────────────

def save_player_games(entries: list[dict]) -> None:
    """
    Upsert entries into player_games.
    Each entry: {username, game_id, color}.
    """
    if not entries:
        return
    try:
        client = _get_client()
        client.table("player_games").upsert(
            entries, on_conflict="username,game_id"
        ).execute()
        log.info(f"[player_games] saved {len(entries)} entries")
    except Exception as e:
        log.error(f"[player_games] save_player_games failed: {e}")


# ── analyses table (Claude output cache) ─────────────────────────────────────

def get_cached_analysis(games_hash: str) -> Optional[dict]:
    """Return cached full Claude analysis if fresher than CACHE_TTL_HOURS."""
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
    """Save full Claude analysis result + per-opening stats snapshot."""
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


# ── opening_knowledge table ───────────────────────────────────────────────────

def get_opening_knowledge(eco: str, color: str) -> Optional[dict]:
    """Return cached opening knowledge for this ECO+color, or None if not yet generated."""
    try:
        client = _get_client()
        resp = (
            client.table("opening_knowledge")
            .select("strategic_goal, key_plans, transition_point, tactical_themes, common_mistakes")
            .eq("eco", eco)
            .eq("color", color)
            .limit(1)
            .execute()
        )
        if resp.data:
            log.info(f"[opening_knowledge] cache hit: {eco}/{color}")
            return resp.data[0]
        log.info(f"[opening_knowledge] cache miss: {eco}/{color}")
        return None
    except Exception as e:
        log.error(f"[opening_knowledge] get failed: {e}")
        return None


def save_opening_knowledge(eco: str, opening_name: str, color: str, knowledge: dict) -> None:
    """Upsert generated opening knowledge. knowledge = {strategic_goal, key_plans, ...}"""
    try:
        client = _get_client()
        client.table("opening_knowledge").upsert(
            {
                "eco": eco,
                "opening_name": opening_name,
                "color": color,
                **knowledge,
            },
            on_conflict="eco,color",
        ).execute()
        log.info(f"[opening_knowledge] saved: {eco}/{color} ({opening_name})")
    except Exception as e:
        log.error(f"[opening_knowledge] save failed: {e}")


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
