"""
Chess analysis logic using python-chess and Stockfish.
Evaluates positions for both white and black, calculates ACPL, and identifies key moments.
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
    eval_before: float   # centipawns from that side's perspective
    eval_after: float
    best_move_san: str | None
    is_user_move: bool


@dataclass
class GameAnalysis:
    game: Game
    move_evals: list[MoveEval] = field(default_factory=list)
    acpl_white: float = 0.0
    acpl_black: float = 0.0
    key_positions_white: list[KeyPosition] = field(default_factory=list)
    key_positions_black: list[KeyPosition] = field(default_factory=list)

    @property
    def acpl(self) -> float:
        """ACPL from the querying user's perspective."""
        return self.acpl_white if self.game.color == "white" else self.acpl_black

    @property
    def key_positions(self) -> list[KeyPosition]:
        """Key positions from the querying user's perspective."""
        return self.key_positions_white if self.game.color == "white" else self.key_positions_black


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

    return OpeningStats(
        name=games[0].opening_name,
        eco=games[0].eco,
        games=len(games),
        wins=wins,
        draws=draws,
        losses=losses,
        avg_opponent_rating=avg_rating,
    )


def _score_to_cp_abs(pov_score: chess.engine.PovScore) -> float:
    """
    Convert engine PovScore to absolute centipawns from white's perspective.
    Positive = good for white, negative = good for black.
    """
    white_score = pov_score.white()
    if white_score.is_mate():
        m = white_score.mate()
        return 3000.0 if (m is not None and m > 0) else -3000.0
    cp = white_score.score(mate_score=3000)
    return float(cp) if cp is not None else 0.0


async def analyze_games_with_stockfish(
    games: list[Game],
    depth: int = 15,
    max_games: int = 5,
    existing_db_rows: dict | None = None,
) -> tuple[list[GameAnalysis], list[GameAnalysis]]:
    """
    Analyze games with Stockfish. Games already in existing_db_rows are reconstructed
    from DB data; the rest are analyzed fresh (up to max_games).

    Returns (all_analyses, newly_analyzed):
      - all_analyses: GameAnalysis for every game (from DB or fresh Stockfish)
      - newly_analyzed: only the ones freshly run through Stockfish
    """
    existing_db_rows = existing_db_rows or {}

    # Reconstruct GameAnalysis from DB for already-analyzed games
    results: list[GameAnalysis] = []
    for game in games:
        if game.game_id in existing_db_rows:
            row = existing_db_rows[game.game_id]
            ga = GameAnalysis(game=game)
            ga.acpl_white = row.get("acpl_white") or 0.0
            ga.acpl_black = row.get("acpl_black") or 0.0
            ga.key_positions_white = [
                KeyPosition(**p) for p in (row.get("key_positions_white") or [])
            ]
            ga.key_positions_black = [
                KeyPosition(**p) for p in (row.get("key_positions_black") or [])
            ]
            results.append(ga)

    # Determine which games still need Stockfish
    cached_ids = set(existing_db_rows.keys())
    uncached = [g for g in games if g.game_id not in cached_ids]

    if not uncached:
        return results, []

    sf_path = _find_stockfish()
    if sf_path is None:
        return results, []

    # Pick a representative sample from uncached games
    step = max(1, len(uncached) // max_games)
    selected = uncached[::step][:max_games]

    newly_analyzed: list[GameAnalysis] = []

    try:
        _, engine = await chess.engine.popen_uci(sf_path)
        try:
            for game in selected:
                analysis = await _analyze_single_game(game, engine, depth)
                if analysis:
                    results.append(analysis)
                    newly_analyzed.append(analysis)
        finally:
            await engine.quit()
    except Exception:
        pass

    return results, newly_analyzed


async def _analyze_single_game(
    game: Game,
    engine: chess.engine.Protocol,
    depth: int,
) -> GameAnalysis | None:
    """
    Analyze a single game for BOTH sides using Stockfish.
    All evals are stored as absolute (positive = good for white).
    """
    try:
        pgn_io = io.StringIO(game.pgn)
        pgn_game = chess.pgn.read_game(pgn_io)
        if pgn_game is None:
            return None

        board = pgn_game.board()
        moves = list(pgn_game.mainline_moves())
        if not moves:
            return None

        analysis_obj = GameAnalysis(game=game)
        white_move_evals: list[MoveEval] = []
        black_move_evals: list[MoveEval] = []

        # Track previous absolute eval to detect big swings
        prev_eval_abs: float | None = None

        for i, move in enumerate(moves):
            move_number = i // 2 + 1
            is_white_move = (i % 2 == 0)

            # Evaluate at key moments for both sides
            should_eval = 8 <= move_number <= 30 and move_number % 5 == 0

            fen_before = board.fen()

            if should_eval:
                try:
                    result_before = await engine.analyse(
                        board, chess.engine.Limit(depth=depth)
                    )
                    eval_before_abs = _score_to_cp_abs(result_before["score"])
                    pv = result_before.get("pv", [])
                    best_move_obj = pv[0] if pv else None
                    best_move_san = board.san(best_move_obj) if best_move_obj else None
                except Exception:
                    eval_before_abs = prev_eval_abs or 0.0
                    best_move_san = None

                move_san = board.san(move)
                board.push(move)
                fen_after = board.fen()

                try:
                    result_after = await engine.analyse(
                        board, chess.engine.Limit(depth=depth)
                    )
                    eval_after_abs = _score_to_cp_abs(result_after["score"])
                except Exception:
                    eval_after_abs = eval_before_abs

                if is_white_move:
                    # White cp_loss: eval dropped (white made a mistake)
                    swing = eval_before_abs - eval_after_abs
                    me = MoveEval(
                        move_number=move_number,
                        move_san=move_san,
                        fen_before=fen_before,
                        fen_after=fen_after,
                        eval_before=eval_before_abs,
                        eval_after=eval_after_abs,
                        best_move_san=best_move_san,
                        is_user_move=(game.color == "white"),
                    )
                    white_move_evals.append(me)

                    if prev_eval_abs is not None and swing > 150:
                        analysis_obj.key_positions_white.append(KeyPosition(
                            fen=fen_before,
                            move_number=move_number,
                            comment=_describe_swing(swing, move_san, move_number, "white"),
                            eval_before=eval_before_abs,
                            eval_after=eval_after_abs,
                            best_move_san=best_move_san,
                            move_played_san=move_san,
                            game_id=game.game_id,
                        ))
                else:
                    # Black cp_loss: eval rose (white gained = black made a mistake)
                    swing = eval_after_abs - eval_before_abs
                    # Store evals from black's perspective (negated) for consistent ACPL formula
                    me = MoveEval(
                        move_number=move_number,
                        move_san=move_san,
                        fen_before=fen_before,
                        fen_after=fen_after,
                        eval_before=-eval_before_abs,
                        eval_after=-eval_after_abs,
                        best_move_san=best_move_san,
                        is_user_move=(game.color == "black"),
                    )
                    black_move_evals.append(me)

                    if prev_eval_abs is not None and swing > 150:
                        analysis_obj.key_positions_black.append(KeyPosition(
                            fen=fen_before,
                            move_number=move_number,
                            comment=_describe_swing(swing, move_san, move_number, "black"),
                            eval_before=-eval_before_abs,
                            eval_after=-eval_after_abs,
                            best_move_san=best_move_san,
                            move_played_san=move_san,
                            game_id=game.game_id,
                        ))

                prev_eval_abs = eval_after_abs
            else:
                board.push(move)

        # ACPL: average centipawn loss using max(0, eval_before - eval_after)
        # Works for both sides since black evals are stored negated
        if white_move_evals:
            losses = [max(0.0, me.eval_before - me.eval_after) for me in white_move_evals]
            analysis_obj.acpl_white = sum(losses) / len(losses)

        if black_move_evals:
            losses = [max(0.0, me.eval_before - me.eval_after) for me in black_move_evals]
            analysis_obj.acpl_black = sum(losses) / len(losses)

        analysis_obj.move_evals = white_move_evals + black_move_evals
        return analysis_obj

    except Exception:
        return None


def _describe_swing(swing: float, move_san: str, move_number: int, color: str) -> str:
    pawns = abs(swing) / 100
    return (
        f"Move {move_number}: After {move_san}, "
        f"{'white' if color == 'white' else 'black'} lost {pawns:.1f} pawns."
    )


def aggregate_analysis(
    game_analyses: list[GameAnalysis],
) -> tuple[float, list[KeyPosition]]:
    """
    Aggregate multiple game analyses into overall ACPL and key positions.
    Uses the .acpl and .key_positions properties which respect the user's color.
    Returns (avg_acpl, top_key_positions).
    """
    if not game_analyses:
        return 0.0, []

    all_acpl = [ga.acpl for ga in game_analyses if ga.acpl > 0]
    avg_acpl = sum(all_acpl) / len(all_acpl) if all_acpl else 0.0

    all_positions: list[KeyPosition] = []
    for ga in game_analyses:
        all_positions.extend(ga.key_positions)

    all_positions.sort(
        key=lambda p: abs((p.eval_after or 0) - (p.eval_before or 0)), reverse=True
    )
    return avg_acpl, all_positions[:3]


def determine_verdict(stats: OpeningStats, avg_acpl: float) -> tuple[str, str]:
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
