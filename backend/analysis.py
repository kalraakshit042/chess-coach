"""
Chess analysis logic using python-chess and Stockfish.
Evaluates positions, calculates ACPL, and identifies tactical moments.
"""
import io
import os
import shutil
from dataclasses import dataclass, field

import chess
import chess.engine
import chess.pgn

from models import Game, KeyPosition, OpeningStats

# Stockfish binary path — tries common locations
STOCKFISH_PATHS = [
    "/opt/homebrew/bin/stockfish",
    "/usr/local/bin/stockfish",
    "/usr/bin/stockfish",
    "stockfish",  # if on PATH
]


def _find_stockfish() -> str | None:
    for path in STOCKFISH_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return shutil.which("stockfish")


@dataclass
class MoveEval:
    move_number: int
    move_san: str
    fen_before: str
    fen_after: str
    eval_before: float  # centipawns from user's perspective
    eval_after: float
    best_move_san: str | None  # Stockfish's preferred move
    is_user_move: bool


@dataclass
class GameAnalysis:
    game: Game
    move_evals: list[MoveEval] = field(default_factory=list)
    acpl: float = 0.0
    missed_tactics: list[MoveEval] = field(default_factory=list)
    key_positions: list[KeyPosition] = field(default_factory=list)


def compute_opening_stats(games: list[Game]) -> OpeningStats:
    """Compute win/draw/loss stats for a list of games under one opening."""
    wins = draws = losses = 0
    ratings = []
    color = games[0].color if games else "white"

    for g in games:
        r = g.result
        if (r == "1-0" and color == "white") or (r == "0-1" and color == "black"):
            wins += 1
        elif r == "1/2-1/2":
            draws += 1
        else:
            losses += 1
        if g.opponent_rating:
            ratings.append(g.opponent_rating)

    avg_rating = sum(ratings) / len(ratings) if ratings else None

    name = games[0].opening_name
    eco = games[0].eco

    return OpeningStats(
        name=name,
        eco=eco,
        games=len(games),
        wins=wins,
        draws=draws,
        losses=losses,
        avg_opponent_rating=avg_rating,
    )


def _score_to_cp(score: chess.engine.Score, pov: chess.Color) -> float:
    """Convert an engine Score to centipawns from the given player's perspective."""
    if score.is_mate():
        mate_moves = score.mate()
        if mate_moves is None:
            return 0.0
        cp = 3000 if mate_moves > 0 else -3000
        return float(cp) if pov == chess.WHITE else float(-cp)
    cp = score.score(mate_score=3000)
    if cp is None:
        return 0.0
    return float(cp) if pov == chess.WHITE else float(-cp)


async def analyze_games_with_stockfish(
    games: list[Game],
    depth: int = 15,
    max_games: int = 5,
    cached_game_analyses: dict | None = None,
) -> tuple[list[GameAnalysis], list[dict]]:
    """
    Run Stockfish analysis on up to `max_games` games, skipping any with cached results.
    Returns (game_analyses, new_cache_rows) where new_cache_rows are ready to save to DB.
    """
    cached_game_analyses = cached_game_analyses or {}

    # Reconstruct GameAnalysis objects from cache
    results: list[GameAnalysis] = []
    for game in games:
        if game.game_id in cached_game_analyses:
            cached = cached_game_analyses[game.game_id]
            ga = GameAnalysis(game=game)
            ga.acpl = cached.get("acpl") or 0.0
            raw_positions = cached.get("key_positions") or []
            ga.key_positions = [KeyPosition(**p) for p in raw_positions]
            results.append(ga)

    # Determine which games still need Stockfish
    cached_ids = set(cached_game_analyses.keys())
    uncached = [g for g in games if g.game_id not in cached_ids]

    if not uncached:
        return results, []

    sf_path = _find_stockfish()
    if sf_path is None:
        return results, []

    # Pick representative sample from uncached games
    step = max(1, len(uncached) // max_games)
    selected = uncached[::step][:max_games]

    new_cache_rows: list[dict] = []

    try:
        _, engine = await chess.engine.popen_uci(sf_path)
        try:
            for game in selected:
                analysis = await _analyze_single_game(game, engine, depth)
                if analysis:
                    results.append(analysis)
                    # Prepare cache row for this game
                    new_cache_rows.append({
                        "game_id": game.game_id,
                        "acpl": analysis.acpl if analysis.acpl > 0 else None,
                        "key_positions": [p.model_dump() for p in analysis.key_positions],
                    })
        finally:
            await engine.quit()
    except Exception:
        pass

    return results, new_cache_rows


async def _analyze_single_game(
    game: Game,
    engine: chess.engine.Protocol,
    depth: int,
) -> GameAnalysis | None:
    """Analyze a single game with Stockfish at key moments."""
    try:
        pgn_io = io.StringIO(game.pgn)
        pgn_game = chess.pgn.read_game(pgn_io)
        if pgn_game is None:
            return None

        board = pgn_game.board()
        user_color = chess.WHITE if game.color == "white" else chess.BLACK

        move_evals: list[MoveEval] = []
        analysis_obj = GameAnalysis(game=game)

        moves = list(pgn_game.mainline_moves())
        if not moves:
            return None

        prev_eval: float | None = None

        for i, move in enumerate(moves):
            move_number = i // 2 + 1
            is_user_move = (i % 2 == 0 and game.color == "white") or (
                i % 2 == 1 and game.color == "black"
            )

            should_eval = (
                is_user_move
                and 8 <= move_number <= 30
                and move_number % 5 == 0
            )

            fen_before = board.fen()

            if should_eval:
                try:
                    result_before = await engine.analyse(
                        board, chess.engine.Limit(depth=depth)
                    )
                    eval_before = _score_to_cp(
                        result_before["score"].relative, board.turn
                    )
                    # Get Stockfish's best move from the principal variation
                    pv = result_before.get("pv", [])
                    best_move_obj = pv[0] if pv else None
                    best_move_san = board.san(best_move_obj) if best_move_obj else None
                except Exception:
                    eval_before = prev_eval or 0.0
                    best_move_san = None

                # Get SAN of the move played before pushing
                move_san = board.san(move)
                board.push(move)
                fen_after = board.fen()

                try:
                    result_after = await engine.analyse(
                        board, chess.engine.Limit(depth=depth)
                    )
                    eval_after = _score_to_cp(
                        result_after["score"].relative, board.turn
                    )
                    eval_after_user = -eval_after
                except Exception:
                    eval_after_user = eval_before

                me = MoveEval(
                    move_number=move_number,
                    move_san=move_san,
                    fen_before=fen_before,
                    fen_after=fen_after,
                    eval_before=eval_before,
                    eval_after=eval_after_user,
                    best_move_san=best_move_san,
                    is_user_move=True,
                )
                move_evals.append(me)

                # Detect significant eval swings
                if prev_eval is not None:
                    swing = eval_before - prev_eval
                    if abs(swing) > 150:  # > 1.5 pawn swing
                        analysis_obj.missed_tactics.append(me)
                        kp = KeyPosition(
                            fen=fen_before,
                            move_number=move_number,
                            comment=_describe_swing(swing, move_san, move_number),
                            eval_before=prev_eval,
                            eval_after=eval_before,
                            best_move_san=best_move_san,
                            move_played_san=move_san,
                            game_id=game.game_id,
                        )
                        analysis_obj.key_positions.append(kp)

                prev_eval = eval_after_user
            else:
                board.push(move)

        # Calculate ACPL
        if move_evals:
            cp_losses = [
                max(0.0, me.eval_before - me.eval_after) for me in move_evals
            ]
            analysis_obj.acpl = sum(cp_losses) / len(cp_losses) if cp_losses else 0.0

        analysis_obj.move_evals = move_evals
        return analysis_obj

    except Exception:
        return None


def _describe_swing(swing: float, move_san: str, move_number: int) -> str:
    pawns = abs(swing) / 100
    direction = "dropped" if swing < 0 else "gained"
    return (
        f"Move {move_number}: After {move_san}, evaluation {direction} "
        f"by {pawns:.1f} pawns."
    )


def aggregate_analysis(
    game_analyses: list[GameAnalysis],
) -> tuple[float, list[KeyPosition]]:
    """
    Aggregate multiple game analyses into overall ACPL and key positions.
    Returns (avg_acpl, top_key_positions).
    """
    if not game_analyses:
        return 0.0, []

    all_acpl = [ga.acpl for ga in game_analyses if ga.acpl > 0]
    avg_acpl = sum(all_acpl) / len(all_acpl) if all_acpl else 0.0

    all_positions: list[KeyPosition] = []
    for ga in game_analyses:
        all_positions.extend(ga.key_positions)

    # Sort by magnitude of swing, take top 3
    all_positions.sort(
        key=lambda p: abs((p.eval_after or 0) - (p.eval_before or 0)), reverse=True
    )
    return avg_acpl, all_positions[:3]


def determine_verdict(
    stats: OpeningStats, avg_acpl: float
) -> tuple[str, str]:
    win_rate = stats.wins / stats.games if stats.games > 0 else 0.0
    score = win_rate + (stats.draws / stats.games * 0.5 if stats.games > 0 else 0)

    if avg_acpl > 0:
        if avg_acpl > 80:
            score -= 0.15
        elif avg_acpl > 50:
            score -= 0.05

    if score >= 0.55:
        return "Strong", "green"
    elif score >= 0.40:
        return "Needs Work", "yellow"
    else:
        return "Weak", "red"
