"""
Lichess API integration for fetching and parsing user games.
"""
import asyncio
import io
import re
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

import chess.pgn
import httpx

from models import Game

LICHESS_API_BASE = "https://lichess.org/api"
RATE_LIMIT_DELAY = 1.0  # seconds between requests


def _parse_pgn_game(pgn_text: str) -> Game | None:
    """Parse a PGN string into a Game model."""
    try:
        pgn_io = io.StringIO(pgn_text)
        game = chess.pgn.read_game(pgn_io)
        if game is None:
            return None

        headers = game.headers

        result = headers.get("Result", "*")
        white = headers.get("White", "")
        black = headers.get("Black", "")
        white_elo = headers.get("WhiteElo", "?")
        black_elo = headers.get("BlackElo", "?")
        opening = headers.get("Opening", "Unknown Opening")
        eco = headers.get("ECO", "?")
        time_control = headers.get("TimeControl", None)

        # Determine user color from the perspective of who we're analyzing
        # We'll set color based on the PGN headers — caller resolves which side the user is
        # For now parse both sides; caller filters by username
        user_color = headers.get("_UserColor", "white")  # injected by caller

        if user_color == "white":
            opponent_rating_str = black_elo
        else:
            opponent_rating_str = white_elo

        try:
            opponent_rating = int(opponent_rating_str) if opponent_rating_str != "?" else None
        except (ValueError, TypeError):
            opponent_rating = None

        # Extract moves
        moves = []
        board = game.board()
        for move in game.mainline_moves():
            moves.append(board.san(move))
            board.push(move)

        return Game(
            pgn=pgn_text,
            result=result,
            color=user_color,
            opening_name=opening,
            eco=eco,
            opponent_rating=opponent_rating,
            time_control=time_control,
            moves=moves,
        )
    except Exception:
        return None


async def fetch_user_games(
    username: str,
    months: int = 12,
    speed: str = "all",
    progress_callback=None,
) -> tuple[list[Game], int | None]:
    """
    Fetch rated games for a Lichess user from the past `months` months.
    Returns (games, user_rating).
    Raises ValueError for unknown user or private account.
    """
    since_dt = datetime.now(timezone.utc) - timedelta(days=months * 30)
    since_ms = int(since_dt.timestamp() * 1000)

    url = f"{LICHESS_API_BASE}/games/user/{username}"
    params = {
        "rated": "true",
        "since": since_ms,
        "opening": "true",
        "clocks": "false",
        "evals": "false",
        "pgnInJson": "false",
        "max": 500,  # cap at 500 for reasonable performance
    }
    if speed != "all":
        params["perfType"] = speed

    headers = {
        "Accept": "application/x-ndjson",
    }

    # First check if user exists
    user_rating = None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            user_resp = await client.get(
                f"{LICHESS_API_BASE}/user/{username}",
                headers={"Accept": "application/json"},
            )
            if user_resp.status_code == 404:
                raise ValueError(f"User '{username}' not found on Lichess.")
            if user_resp.status_code != 200:
                raise ValueError(f"Could not fetch user data (HTTP {user_resp.status_code}).")

            user_data = user_resp.json()
            if user_data.get("disabled") or user_data.get("closed"):
                raise ValueError(f"Account '{username}' is disabled or closed.")

            # Try to get a representative rating (prefer classical > rapid > blitz > bullet)
            perfs = user_data.get("perfs", {})
            for tc in ("classical", "rapid", "blitz", "bullet"):
                if tc in perfs and perfs[tc].get("games", 0) > 0:
                    user_rating = perfs[tc]["rating"]
                    break

    except httpx.RequestError as e:
        raise ValueError(f"Network error contacting Lichess: {e}") from e

    # Stream games via NDJSON
    games: list[Game] = []
    raw_pgn_buffer: list[str] = []

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "GET",
                url,
                params=params,
                headers=headers,
            ) as response:
                if response.status_code == 429:
                    raise ValueError("Lichess rate limit hit. Please wait a minute and try again.")
                if response.status_code != 200:
                    raise ValueError(
                        f"Could not fetch games (HTTP {response.status_code}). "
                        "The account may be private."
                    )

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue

                    # NDJSON: each line is a JSON object describing a game
                    import json
                    try:
                        game_data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    game = _parse_ndjson_game(game_data, username)
                    if game is not None:
                        games.append(game)
                        if progress_callback and len(games) % 25 == 0:
                            await progress_callback(len(games))

                    # Respect rate limits
                    if len(games) % 100 == 0 and len(games) > 0:
                        await asyncio.sleep(RATE_LIMIT_DELAY)

    except httpx.RequestError as e:
        raise ValueError(f"Network error fetching games: {e}") from e

    return games, user_rating


def _parse_ndjson_game(data: dict, username: str) -> Game | None:
    """Parse a Lichess NDJSON game object into a Game model."""
    try:
        result_map = {"1-0": "1-0", "0-1": "0-1", "1/2-1/2": "1/2-1/2"}
        winner = data.get("winner")  # "white", "black", or absent (draw)
        status = data.get("status", "")

        if status in ("aborted", "noStart"):
            return None

        # Determine result string
        if winner == "white":
            result = "1-0"
        elif winner == "black":
            result = "0-1"
        else:
            result = "1/2-1/2"

        players = data.get("players", {})
        white_player = players.get("white", {})
        black_player = players.get("black", {})

        white_name = white_player.get("user", {}).get("name", "").lower()
        black_name = black_player.get("user", {}).get("name", "").lower()

        if white_name == username.lower():
            color = "white"
            opponent_rating = black_player.get("rating")
            opponent_name = black_player.get("user", {}).get("name", "?")
        elif black_name == username.lower():
            color = "black"
            opponent_rating = white_player.get("rating")
            opponent_name = white_player.get("user", {}).get("name", "?")
        else:
            return None  # user not in this game (shouldn't happen)

        opening_data = data.get("opening", {})
        opening_name = opening_data.get("name", "Unknown Opening")
        eco = opening_data.get("eco", "?")

        # Reconstruct moves list from moves string
        moves_str = data.get("moves", "")
        moves = moves_str.split() if moves_str else []

        # Build a minimal PGN string for analysis
        white_elo = white_player.get("rating", "?")
        black_elo = black_player.get("rating", "?")
        white_name_display = white_player.get("user", {}).get("name", "?")
        black_name_display = black_player.get("user", {}).get("name", "?")

        pgn = _build_pgn(
            white_name_display,
            black_name_display,
            str(white_elo),
            str(black_elo),
            opening_name,
            eco,
            result,
            moves_str,
            data.get("createdAt", ""),
        )

        time_control_data = data.get("clock", {})
        if time_control_data:
            initial = time_control_data.get("initial", 0)
            increment = time_control_data.get("increment", 0)
            time_control = f"{initial}+{increment}"
        else:
            time_control = data.get("speed", None)

        # Parse played_at date
        played_at = None
        created_at_ms = data.get("createdAt", "")
        if created_at_ms:
            try:
                from datetime import datetime, timezone
                ts = int(created_at_ms) / 1000
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                played_at = dt.strftime("%b %d, %Y")
            except Exception:
                pass

        game_id = data.get("id", "")

        return Game(
            pgn=pgn,
            result=result,
            color=color,
            opening_name=opening_name,
            eco=eco,
            opponent_rating=opponent_rating,
            opponent_name=opponent_name,
            time_control=time_control,
            moves=moves[:40],  # keep first 40 moves for analysis
            game_id=game_id,
            played_at=played_at,
        )
    except Exception:
        return None


def _build_pgn(
    white: str,
    black: str,
    white_elo: str,
    black_elo: str,
    opening: str,
    eco: str,
    result: str,
    moves_str: str,
    created_at: str,
) -> str:
    """Build a PGN string from game data."""
    date_str = "????.??.??"
    if created_at:
        try:
            ts = int(created_at) / 1000
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            date_str = dt.strftime("%Y.%m.%d")
        except Exception:
            pass

    # Format moves into numbered PGN format
    moves = moves_str.split() if moves_str else []
    pgn_moves = []
    for i, move in enumerate(moves):
        if i % 2 == 0:
            pgn_moves.append(f"{i // 2 + 1}.")
        pgn_moves.append(move)

    moves_text = " ".join(pgn_moves)

    return (
        f'[White "{white}"]\n'
        f'[Black "{black}"]\n'
        f'[WhiteElo "{white_elo}"]\n'
        f'[BlackElo "{black_elo}"]\n'
        f'[Opening "{opening}"]\n'
        f'[ECO "{eco}"]\n'
        f'[Result "{result}"]\n'
        f'[Date "{date_str}"]\n'
        f"\n{moves_text} {result}\n"
    )


def group_games_by_opening(
    games: list[Game], min_games: int = 3
) -> dict[str, list[Game]]:
    """
    Group games by ECO code / opening name.
    Returns a dict mapping opening_key -> list of games.
    Only includes openings with >= min_games games.
    """
    groups: dict[str, list[Game]] = {}

    for game in games:
        # Use ECO + first part of opening name as key
        # e.g. "B20 Sicilian Defense" → group all Sicilian variants together at ECO level
        eco_prefix = game.eco[:3] if game.eco and game.eco != "?" else "UNK"
        # Use the full opening name from Lichess but normalize it
        key = f"{eco_prefix} {game.opening_name}"
        if key not in groups:
            groups[key] = []
        groups[key].append(game)

    # Filter out openings with too few games
    return {k: v for k, v in groups.items() if len(v) >= min_games}
