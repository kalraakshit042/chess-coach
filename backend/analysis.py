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

from models import CoachingDiagnosis, Game, KeyPosition, OpeningStats

# Stockfish binary path — tries common locations
STOCKFISH_PATHS = [
    "/opt/homebrew/bin/stockfish",
    "/usr/local/bin/stockfish",
    "/usr/bin/stockfish",
    "stockfish",  # if on PATH
]


def find_stockfish() -> str | None:
    import logging
    _log = logging.getLogger("analysis")
    for path in STOCKFISH_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            _log.info("Stockfish found at: %s", path)
            return path
    result = shutil.which("stockfish")
    if result:
        _log.info("Stockfish found via PATH: %s", result)
    else:
        _log.error("Stockfish not found. Tried paths: %s. shutil.which returned None.", STOCKFISH_PATHS)
    return result

_find_stockfish = find_stockfish  # internal alias


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

    selected = uncached  # analyse every uncached game — no sampling

    newly_analyzed: list[GameAnalysis] = []

    try:
        _, engine = await chess.engine.popen_uci(sf_path)
        try:
            for game in selected:
                analysis = await analyze_single_game(game, engine, depth)
                if analysis:
                    results.append(analysis)
                    newly_analyzed.append(analysis)
        finally:
            await engine.quit()
    except Exception:
        pass

    return results, newly_analyzed


async def analyze_single_game(
    game: Game,
    engine: chess.engine.Protocol,
    depth: int,
) -> GameAnalysis | None:
    """
    Analyze a single game for BOTH sides using Stockfish.
    Evaluates every position — no sampling. Each position is evaluated once
    and reused as eval_before/eval_after for adjacent moves.
    All evals stored as absolute centipawns (positive = good for white).
    """
    SKIP_MOVES = 4        # ignore first 4 full moves (opening book)
    BLUNDER_CP  = 150     # centipawn threshold to record a key position

    try:
        pgn_io = io.StringIO(game.pgn)
        pgn_game = chess.pgn.read_game(pgn_io)
        if pgn_game is None:
            return None

        board = pgn_game.board()
        moves = list(pgn_game.mainline_moves())
        if not moves:
            return None

        # ── Pass 1: collect all board states + move metadata ──────────────
        boards: list[chess.Board] = [board.copy()]
        move_sans:       list[str]  = []
        is_white_moves:  list[bool] = []
        move_numbers:    list[int]  = []

        for i, move in enumerate(moves):
            move_sans.append(board.san(move))
            is_white_moves.append(i % 2 == 0)
            move_numbers.append(i // 2 + 1)
            board.push(move)
            boards.append(board.copy())

        # ── Pass 2: evaluate every position exactly once ──────────────────
        evals: list[tuple[float, str | None]] = []
        for b in boards:
            try:
                result = await engine.analyse(b, chess.engine.Limit(depth=depth))
                ev = _score_to_cp_abs(result["score"])
                pv = result.get("pv", [])
                best_obj = pv[0] if pv else None
                best_san = b.san(best_obj) if best_obj else None
            except Exception:
                ev = 0.0
                best_san = None
            evals.append((ev, best_san))

        # ── Pass 3: compute cp-loss per move, record key positions ─────────
        analysis_obj = GameAnalysis(game=game)
        white_move_evals: list[MoveEval] = []
        black_move_evals: list[MoveEval] = []

        for i, move in enumerate(moves):
            move_number = move_numbers[i]
            if move_number <= SKIP_MOVES:
                continue

            eval_before_abs, best_san = evals[i]
            eval_after_abs, _         = evals[i + 1]
            is_white  = is_white_moves[i]
            move_san  = move_sans[i]
            fen_before = boards[i].fen()
            fen_after  = boards[i + 1].fen()

            if is_white:
                swing = eval_before_abs - eval_after_abs   # positive = white lost eval
                me = MoveEval(
                    move_number=move_number, move_san=move_san,
                    fen_before=fen_before, fen_after=fen_after,
                    eval_before=eval_before_abs, eval_after=eval_after_abs,
                    best_move_san=best_san, is_user_move=(game.color == "white"),
                )
                white_move_evals.append(me)
                if swing > BLUNDER_CP:
                    analysis_obj.key_positions_white.append(KeyPosition(
                        fen=fen_before, move_number=move_number,
                        comment=_describe_swing(swing, move_san, move_number, "white"),
                        eval_before=eval_before_abs, eval_after=eval_after_abs,
                        best_move_san=best_san, move_played_san=move_san,
                        game_id=game.game_id,
                    ))
            else:
                swing = eval_after_abs - eval_before_abs   # positive = black lost eval
                me = MoveEval(
                    move_number=move_number, move_san=move_san,
                    fen_before=fen_before, fen_after=fen_after,
                    eval_before=-eval_before_abs, eval_after=-eval_after_abs,
                    best_move_san=best_san, is_user_move=(game.color == "black"),
                )
                black_move_evals.append(me)
                if swing > BLUNDER_CP:
                    analysis_obj.key_positions_black.append(KeyPosition(
                        fen=fen_before, move_number=move_number,
                        comment=_describe_swing(swing, move_san, move_number, "black"),
                        eval_before=-eval_before_abs, eval_after=-eval_after_abs,
                        best_move_san=best_san, move_played_san=move_san,
                        game_id=game.game_id,
                    ))

        # ACPL: avg centipawn loss (max 0 so improvements don't cancel mistakes)
        if white_move_evals:
            wl = [max(0.0, me.eval_before - me.eval_after) for me in white_move_evals]
            analysis_obj.acpl_white = sum(wl) / len(wl)
        if black_move_evals:
            bl = [max(0.0, me.eval_before - me.eval_after) for me in black_move_evals]
            analysis_obj.acpl_black = sum(bl) / len(bl)

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


def diagnose_coaching(
    game_analyses: list[GameAnalysis],
    opening_name: str,
) -> CoachingDiagnosis:
    """
    Classify where and how a player goes wrong in an opening, and recommend what to study.

    Logic:
    - Phase is determined by where key positions (>150cp swings) cluster
    - Mistake type: many blunders/game → tactics; few blunders but high ACPL → positional drift
    - Opening phase (<= move 14) always → study theory
    - Endgame phase (> move 30) → endgame technique
    """
    all_positions: list[KeyPosition] = []
    for ga in game_analyses:
        all_positions.extend(ga.key_positions)

    # Phase distribution
    opening_pos  = [p for p in all_positions if p.move_number <= 14]
    mid_pos      = [p for p in all_positions if 15 <= p.move_number <= 30]
    endgame_pos  = [p for p in all_positions if p.move_number > 30]
    phase_dist   = {"opening": len(opening_pos), "middlegame": len(mid_pos), "endgame": len(endgame_pos)}

    # Dominant phase
    if all_positions:
        avg_mistake_move = sum(p.move_number for p in all_positions) / len(all_positions)
        dominant_phase = max(phase_dist, key=phase_dist.get)
    else:
        avg_mistake_move = None
        dominant_phase = "middlegame"

    # Win / loss split
    def _is_win(ga: GameAnalysis) -> bool:
        r = ga.game.result
        return (r == "1-0" and ga.game.color == "white") or (r == "0-1" and ga.game.color == "black")
    def _is_loss(ga: GameAnalysis) -> bool:
        r = ga.game.result
        return (r == "0-1" and ga.game.color == "white") or (r == "1-0" and ga.game.color == "black")

    wins   = [ga for ga in game_analyses if _is_win(ga)]
    losses = [ga for ga in game_analyses if _is_loss(ga)]
    draws  = [ga for ga in game_analyses if not _is_win(ga) and not _is_loss(ga)]

    win_acpls  = [ga.acpl for ga in wins   if ga.acpl > 0]
    loss_acpls = [ga.acpl for ga in losses if ga.acpl > 0]
    win_avg_acpl  = round(sum(win_acpls)  / len(win_acpls),  1) if win_acpls  else None
    loss_avg_acpl = round(sum(loss_acpls) / len(loss_acpls), 1) if loss_acpls else None

    # Critical position: single worst moment across all games
    critical_position = None
    if all_positions:
        critical_position = max(
            all_positions,
            key=lambda p: abs((p.eval_after or 0) - (p.eval_before or 0))
        )

    # Classify mistake type and build recommendation
    move_str = f"around move {round(avg_mistake_move)}" if avg_mistake_move else "in the game"
    blunders_per_game = len(all_positions) / max(len(game_analyses), 1)

    if dominant_phase == "opening" or (avg_mistake_move and avg_mistake_move <= 14):
        outcome_type  = "opening_theory"
        outcome_label = "Study Opening Theory"
        outcome_explanation = (
            f"Your mistakes in the {opening_name} consistently happen early ({move_str}), "
            f"before the middlegame begins. You're likely running out of preparation and "
            f"playing unfamiliar positions from memory. The fix is targeted: learn the "
            f"critical lines you face most often, focusing on why each move is played — "
            f"not just what to play."
        )

    elif dominant_phase == "endgame":
        outcome_type  = "endgame_technique"
        outcome_label = "Study Endgame Technique"
        outcome_explanation = (
            f"You're navigating the {opening_name} well through the opening and middlegame, "
            f"but losing ground late in the game ({move_str}). The positions from this "
            f"opening lead to specific endgame types — study those. Converting a winning "
            f"endgame or defending a difficult one is a skill that compounds across all your games."
        )

    elif blunders_per_game >= 0.4:
        # Many sudden >150cp blunders → tactical problem
        outcome_type  = "tactics"
        outcome_label = "Drill Tactics"
        outcome_explanation = (
            f"In the {opening_name}, you're losing material suddenly {move_str} — "
            f"averaging {blunders_per_game:.1f} serious blunders per game. "
            f"These are tactical oversights: missed threats, undefended pieces, forks or pins "
            f"you didn't see coming. The opening creates sharp positions where one missed tactic "
            f"ends the game. Drill the tactical patterns common in this structure."
        )

    else:
        # High ACPL but few big swings → positional drift
        outcome_type  = "positional_plans"
        outcome_label = "Study Typical Plans"
        outcome_explanation = (
            f"You're not making one catastrophic mistake — you're drifting gradually in the "
            f"middlegame of the {opening_name}. You reach a playable position but without a "
            f"clear plan, and slowly fall behind. Study the typical ideas in this structure: "
            f"which pawn breaks to aim for, where to place your pieces, and what your opponent "
            f"is trying to do so you can stop it."
        )

    return CoachingDiagnosis(
        outcome_type=outcome_type,
        outcome_label=outcome_label,
        outcome_explanation=outcome_explanation,
        dominant_phase=dominant_phase,
        avg_mistake_move=round(avg_mistake_move, 1) if avg_mistake_move else None,
        phase_distribution=phase_dist,
        wins=len(wins),
        losses=len(losses),
        draws=len(draws),
        win_avg_acpl=win_avg_acpl,
        loss_avg_acpl=loss_avg_acpl,
        critical_position=critical_position,
    )


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
