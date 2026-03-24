"""
FastAPI backend for Chess Coach.
Fetches Lichess games, runs Stockfish analysis, and generates coaching with Claude.
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
import json

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("main")

import chess.engine
from analysis import (
    GameAnalysis,
    aggregate_analysis,
    analyze_games_with_stockfish,
    analyze_single_game,
    compute_opening_stats,
    determine_verdict,
    diagnose_coaching,
    find_stockfish,
)
from claude_coach import (
    annotate_moves, batch_analyze_openings, build_move_index,
    coach_opening, generate_opening_knowledge,
)
from database import (
    compute_games_hash,
    get_cached_analysis,
    get_existing_game_ids,
    get_games_for_opening,
    get_stockfish_analyses,
    save_all_games_batch,
    save_analysis,
    save_stockfish_analyses,
    save_player_games,
    upsert_lichess_player,
    get_analysis_history,
    get_opening_trends,
)
from lichess import fetch_user_games, group_games_by_opening
from models import (
    AnalyseOpeningRequest,
    AnalysisResponse,
    AnalyzeRequest,
    KeyPosition,
    OpeningAnalysis,
    OpeningAnalysisResult,
    OpeningOverview,
    OpeningStats,
    OverviewRequest,
    OverviewResponse,
    Game,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Chess Coach API",
    description="AI-powered chess coaching using Lichess game history and Claude.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "2.0.0"}


@app.post("/overview")
async def overview(request: OverviewRequest):
    """
    Phase 1: Fetch games, store metadata, return opening stats with no Stockfish.
    Fast — just stats from Lichess data + cached ACPL if available.
    """
    games, user_rating = await fetch_user_games(
        request.username, months=request.months, speed=request.speed
    )
    if not games:
        return JSONResponse(
            status_code=404,
            content={"detail": f"No rated games found for '{request.username}'."},
        )

    upsert_lichess_player(request.username)

    all_game_ids = [g.game_id for g in games if g.game_id]

    # Save new game metadata to DB
    existing_ids = get_existing_game_ids(all_game_ids)
    new_games = [g for g in games if g.game_id and g.game_id not in existing_ids]
    if new_games:
        save_all_games_batch([_build_basic_game_row(g, request.username) for g in new_games])

    # Save player_games
    save_player_games([
        {"username": request.username.lower(), "game_id": g.game_id, "color": g.color}
        for g in games if g.game_id
    ])

    # Load cached Stockfish ACPL for all games
    sf_cache = get_stockfish_analyses(all_game_ids)  # game_id -> {acpl_white, acpl_black}

    # Group by opening (min 2 games to filter noise)
    white_games = [g for g in games if g.color == "white"]
    black_games = [g for g in games if g.color == "black"]
    white_groups = group_games_by_opening(white_games, min_games=2)
    black_groups = group_games_by_opening(black_games, min_games=2)

    def build_overview(groups: dict, color: str) -> list[OpeningOverview]:
        overviews = []
        for key, og in sorted(groups.items(), key=lambda x: len(x[1]), reverse=True):
            stats = compute_opening_stats(og)
            game_ids = [g.game_id for g in og if g.game_id]

            # Compute ACPL from cached analyses
            acpl_field = "acpl_white" if color == "white" else "acpl_black"
            acpl_values = [
                sf_cache[gid][acpl_field]
                for gid in game_ids
                if gid in sf_cache and sf_cache[gid].get(acpl_field)
            ]
            avg_acpl = sum(acpl_values) / len(acpl_values) if acpl_values else None

            uncached_count = sum(1 for gid in game_ids if gid not in sf_cache)
            estimated_secs = uncached_count * 4

            overviews.append(OpeningOverview(
                key=key,
                name=stats.name,
                eco=stats.eco,
                color=color,
                games=stats.games,
                wins=stats.wins,
                draws=stats.draws,
                losses=stats.losses,
                avg_opponent_rating=stats.avg_opponent_rating,
                acpl=round(avg_acpl, 1) if avg_acpl is not None else None,
                estimated_analysis_seconds=estimated_secs,
            ))
        return overviews

    return OverviewResponse(
        username=request.username,
        total_games=len(games),
        white_games=len(white_games),
        black_games=len(black_games),
        white_openings=build_overview(white_groups, "white"),
        black_openings=build_overview(black_groups, "black"),
        user_rating=user_rating,
    )


@app.post("/analyse-opening")
async def analyse_opening(request: AnalyseOpeningRequest):
    """
    Phase 2: Run Stockfish on ALL games in a specific opening. SSE streaming.
    Checks stockfish_analysis cache — only runs engine on uncached games.
    """
    async def event_generator():
        try:
            # Load games from DB
            game_rows = get_games_for_opening(
                request.username, request.eco, request.opening_name, request.color
            )
            if not game_rows:
                yield _sse_event("error", {"message": f"No games found for {request.opening_name} as {request.color}."})
                return

            game_ids = [r["game_id"] for r in game_rows]
            sf_cache = get_stockfish_analyses(game_ids)
            uncached_rows = [r for r in game_rows if r["game_id"] not in sf_cache]
            cached_count = len(sf_cache)
            new_count = len(uncached_rows)
            total = len(game_rows)
            estimated_secs = new_count * 4

            yield _sse_event("progress", {
                "step": "starting",
                "message": f"Analysing {total} games — {cached_count} cached, {new_count} new. Estimated: ~{estimated_secs}s",
                "total": total,
                "cached": cached_count,
                "new": new_count,
                "estimated_seconds": estimated_secs,
            })

            # Reconstruct GameAnalysis for cached games
            all_analyses: list[GameAnalysis] = []
            for row in game_rows:
                if row["game_id"] in sf_cache:
                    sf = sf_cache[row["game_id"]]
                    game = _row_to_game(row, request.username, request.color)
                    ga = GameAnalysis(game=game)
                    ga.acpl_white = sf.get("acpl_white") or 0.0
                    ga.acpl_black = sf.get("acpl_black") or 0.0
                    ga.key_positions_white = [KeyPosition(**p) for p in (sf.get("key_positions_white") or [])]
                    ga.key_positions_black = [KeyPosition(**p) for p in (sf.get("key_positions_black") or [])]
                    all_analyses.append(ga)

            # Run Stockfish on uncached games
            if uncached_rows:
                sf_path = find_stockfish()
                if not sf_path:
                    log.error("Stockfish not found. Searched: %s", find_stockfish.__doc__ or "see analysis.py")
                    yield _sse_event("error", {"message": "Stockfish not found on this server."})
                    return

                new_sf_rows: list[dict] = []
                done = 0

                try:
                    _, engine = await chess.engine.popen_uci(sf_path)
                    try:
                        for row in uncached_rows:
                            game = _row_to_game(row, request.username, request.color)
                            analysis = await analyze_single_game(game, engine, depth=12)
                            if analysis:
                                all_analyses.append(analysis)
                                new_sf_rows.append({
                                    "game_id": game.game_id,
                                    "acpl_white": analysis.acpl_white if analysis.acpl_white > 0 else None,
                                    "acpl_black": analysis.acpl_black if analysis.acpl_black > 0 else None,
                                    "key_positions_white": [p.model_dump() for p in analysis.key_positions_white],
                                    "key_positions_black": [p.model_dump() for p in analysis.key_positions_black],
                                })
                            done += 1
                            yield _sse_event("progress", {
                                "step": "analysing",
                                "message": f"Game {done}/{new_count} analysed...",
                                "done": done,
                                "total_new": new_count,
                            })
                    finally:
                        await engine.quit()
                except Exception as e:
                    log.error(f"Stockfish error: {e}")

                save_stockfish_analyses(new_sf_rows)

            avg_acpl, key_positions = aggregate_analysis(all_analyses)
            diagnosis = diagnose_coaching(all_analyses, request.opening_name)

            # ── Opening knowledge — always generated fresh, never from cache ──
            yield _sse_event("progress", {
                "step": "knowledge",
                "message": "Preparing analysis...",
            })
            knowledge = await generate_opening_knowledge(
                request.opening_name, request.eco, request.color
            )

            # ── Claude coaching ───────────────────────────────────────────────
            yield _sse_event("progress", {
                "step": "coaching",
                "message": "Generating coaching insights...",
            })
            insight = await coach_opening(
                opening_name=request.opening_name,
                eco=request.eco,
                color=request.color,
                knowledge=knowledge,
                diagnosis=diagnosis,
                avg_acpl=round(avg_acpl, 1) if avg_acpl > 0 else None,
                games_analysed=len(all_analyses),
            )

            # Annotate move mentions in insight text with links back to real games
            move_index = build_move_index(all_analyses)
            insight.whats_wrong = annotate_moves(insight.whats_wrong, move_index)
            if insight.critical_moment:
                insight.critical_moment = annotate_moves(insight.critical_moment, move_index)
            insight.pattern = annotate_moves(insight.pattern, move_index)

            yield _sse_event("complete", {
                "opening_name": request.opening_name,
                "eco": request.eco,
                "color": request.color,
                "games_analysed": len(all_analyses),
                "avg_acpl": round(avg_acpl, 1) if avg_acpl > 0 else None,
                "key_positions": [p.model_dump() for p in key_positions],
                "diagnosis": diagnosis.model_dump(),
                "insight": insight.model_dump(),
            })

        except Exception as e:
            log.error(f"analyse_opening error: {e}")
            yield _sse_event("error", {"message": f"Analysis failed: {str(e)}"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/analyze/stream")
async def analyze_stream(request: AnalyzeRequest):
    """
    Stream analysis progress as Server-Sent Events (SSE).
    Yields JSON progress updates, then the final result.
    """
    async def event_generator():
        try:
            # Step 1: Fetch games from Lichess
            yield _sse_event("progress", {
                "step": "fetching",
                "message": f"Fetching games for {request.username} from Lichess...",
            })

            games, user_rating = await fetch_user_games(
                request.username, months=request.months, speed=request.speed
            )

            if request.test_mode:
                games = games[:20]

            if not games:
                speed_label = f" ({request.speed})" if request.speed != "all" else ""
                yield _sse_event("error", {
                    "message": f"No rated games found for '{request.username}' in the last {request.months} months{speed_label}."
                })
                return

            # Track this player
            upsert_lichess_player(request.username)

            white_games = [g for g in games if g.color == "white"]
            black_games = [g for g in games if g.color == "black"]

            yield _sse_event("progress", {
                "step": "games_fetched",
                "message": f"Found {len(games)} games ({len(white_games)} as white, {len(black_games)} as black). Checking cache...",
                "total_games": len(games),
                "white_games": len(white_games),
                "black_games": len(black_games),
            })

            # Level 2 cache check — keyed by the actual set of games
            all_game_ids = [g.game_id for g in games if g.game_id]
            games_hash = compute_games_hash(all_game_ids)
            cached = get_cached_analysis(games_hash)
            if cached:
                yield _sse_event("progress", {
                    "step": "fetching",
                    "message": f"Found cached analysis for these {len(games)} games. Loading instantly...",
                })
                yield _sse_event("complete", {**cached, "from_cache": True})
                return

            # Step 2: Group by opening
            white_groups = group_games_by_opening(white_games, min_games=3)
            black_groups = group_games_by_opening(black_games, min_games=3)

            total_openings = len(white_groups) + len(black_groups)
            yield _sse_event("progress", {
                "step": "openings_grouped",
                "message": f"Found {len(white_groups)} white openings and {len(black_groups)} black openings with 3+ games. Checking engine cache...",
                "white_openings_count": len(white_groups),
                "black_openings_count": len(black_groups),
            })

            # Step 3: Save all new game metadata, load existing Stockfish results
            existing_ids = get_existing_game_ids(all_game_ids)
            new_games = [g for g in games if g.game_id and g.game_id not in existing_ids]
            log.info(f"Total games: {len(all_game_ids)} | Already in DB: {len(existing_ids)} | New: {len(new_games)}")

            # Save metadata for new games first so player_games FK is satisfied
            if new_games:
                log.info(f"Saving {len(new_games)} new game metadata rows to all_games...")
                save_all_games_batch([
                    _build_basic_game_row(g, request.username) for g in new_games
                ])

            # Load existing Stockfish results (only games that have been analyzed)
            existing_db_rows = get_stockfish_analyses(all_game_ids)

            new_count = len(new_games)
            analyzed_count = len(existing_db_rows)
            yield _sse_event("progress", {
                "step": "engine_analysis",
                "message": f"{analyzed_count} games have engine analysis cached, {new_count} new games added. Running engine on top openings...",
            })

            white_stats_map = {k: compute_opening_stats(v) for k, v in white_groups.items()}
            black_stats_map = {k: compute_opening_stats(v) for k, v in black_groups.items()}

            white_acpl_map: dict[str, float] = {}
            white_positions_map: dict[str, list[KeyPosition]] = {}
            black_acpl_map: dict[str, float] = {}
            black_positions_map: dict[str, list[KeyPosition]] = {}

            sorted_white = sorted(white_groups.items(), key=lambda x: len(x[1]), reverse=True)
            sorted_black = sorted(black_groups.items(), key=lambda x: len(x[1]), reverse=True)
            engine_openings_limit = 4

            all_newly_analyzed: list[GameAnalysis] = []

            for key, og in sorted_white[:engine_openings_limit]:
                cached_count = sum(1 for g in og if g.game_id in existing_db_rows)
                yield _sse_event("progress", {
                    "step": "engine_analysis",
                    "message": f"Evaluating white opening: {white_stats_map[key].name} ({cached_count}/{min(len(og), 3)} games cached)...",
                })
                analyses, newly = await analyze_games_with_stockfish(
                    og, depth=12, max_games=3, existing_db_rows=existing_db_rows
                )
                all_newly_analyzed.extend(newly)
                acpl, positions = aggregate_analysis(analyses)
                white_acpl_map[key] = acpl
                white_positions_map[key] = positions

            for key, og in sorted_black[:engine_openings_limit]:
                cached_count = sum(1 for g in og if g.game_id in existing_db_rows)
                yield _sse_event("progress", {
                    "step": "engine_analysis",
                    "message": f"Evaluating black opening: {black_stats_map[key].name} ({cached_count}/{min(len(og), 3)} games cached)...",
                })
                analyses, newly = await analyze_games_with_stockfish(
                    og, depth=12, max_games=3, existing_db_rows=existing_db_rows
                )
                all_newly_analyzed.extend(newly)
                acpl, positions = aggregate_analysis(analyses)
                black_acpl_map[key] = acpl
                black_positions_map[key] = positions

            # Persist newly analyzed games to DB
            log.info(f"Saving Stockfish results for {len(all_newly_analyzed)} newly analyzed games...")
            _save_new_game_rows(all_newly_analyzed, request.username)

            # Save player_games join rows for all games
            log.info(f"Saving {len(all_game_ids)} player_games entries...")
            save_player_games([
                {"username": request.username.lower(), "game_id": g.game_id, "color": g.color}
                for g in games if g.game_id
            ])

            # Step 4: Claude analysis
            yield _sse_event("progress", {
                "step": "claude_analysis",
                "message": f"Generating AI coaching for {total_openings} openings...",
                "total_openings": total_openings,
            })

            white_analyses = await batch_analyze_openings(
                opening_groups=white_groups,
                stats_map=white_stats_map,
                acpl_map=white_acpl_map,
                positions_map=white_positions_map,
                user_rating=user_rating,
                color="white",
            )

            yield _sse_event("progress", {
                "step": "claude_analysis",
                "message": "White openings analyzed. Working on black openings...",
            })

            black_analyses = await batch_analyze_openings(
                opening_groups=black_groups,
                stats_map=black_stats_map,
                acpl_map=black_acpl_map,
                positions_map=black_positions_map,
                user_rating=user_rating,
                color="black",
            )

            # Step 5: Assemble final response
            white_opening_analyses = [
                _build_opening_analysis(
                    key,
                    white_stats_map[key],
                    white_analyses.get(key, {}),
                    white_acpl_map.get(key, 0.0),
                    white_positions_map.get(key, []),
                )
                for key in sorted(white_groups.keys(), key=lambda k: white_stats_map[k].games, reverse=True)
            ]

            black_opening_analyses = [
                _build_opening_analysis(
                    key,
                    black_stats_map[key],
                    black_analyses.get(key, {}),
                    black_acpl_map.get(key, 0.0),
                    black_positions_map.get(key, []),
                )
                for key in sorted(black_groups.keys(), key=lambda k: black_stats_map[k].games, reverse=True)
            ]

            response = AnalysisResponse(
                username=request.username,
                total_games=len(games),
                white_games=len(white_games),
                black_games=len(black_games),
                white_openings=white_opening_analyses,
                black_openings=black_opening_analyses,
                user_rating=user_rating,
            )

            result_dict = response.model_dump()
            save_analysis(request.username, request.months, request.speed, games_hash, result_dict)
            yield _sse_event("complete", result_dict)

        except ValueError as e:
            yield _sse_event("error", {"message": str(e)})
        except Exception as e:
            yield _sse_event("error", {"message": f"An unexpected error occurred: {str(e)}"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/analyze")
async def analyze(request: AnalyzeRequest):
    """Non-streaming analysis endpoint."""
    try:
        games, user_rating = await fetch_user_games(
            request.username, months=request.months, speed=request.speed
        )

        if not games:
            raise HTTPException(
                status_code=404,
                detail=f"No rated games found for '{request.username}' in the last {request.months} months.",
            )

        upsert_lichess_player(request.username)

        white_games = [g for g in games if g.color == "white"]
        black_games = [g for g in games if g.color == "black"]
        white_groups = group_games_by_opening(white_games, min_games=3)
        black_groups = group_games_by_opening(black_games, min_games=3)

        white_stats_map = {k: compute_opening_stats(v) for k, v in white_groups.items()}
        black_stats_map = {k: compute_opening_stats(v) for k, v in black_groups.items()}

        all_game_ids = [g.game_id for g in games if g.game_id]
        existing_ids = get_existing_game_ids(all_game_ids)
        new_games = [g for g in games if g.game_id and g.game_id not in existing_ids]

        if new_games:
            save_all_games_batch([
                _build_basic_game_row(g, request.username) for g in new_games
            ])

        existing_db_rows = get_stockfish_analyses(all_game_ids)

        white_acpl_map: dict[str, float] = {}
        white_positions_map: dict[str, list[KeyPosition]] = {}
        black_acpl_map: dict[str, float] = {}
        black_positions_map: dict[str, list[KeyPosition]] = {}
        all_newly_analyzed: list[GameAnalysis] = []

        for key, og in sorted(white_groups.items(), key=lambda x: len(x[1]), reverse=True)[:4]:
            analyses, newly = await analyze_games_with_stockfish(
                og, depth=12, max_games=3, existing_db_rows=existing_db_rows
            )
            all_newly_analyzed.extend(newly)
            acpl, positions = aggregate_analysis(analyses)
            white_acpl_map[key] = acpl
            white_positions_map[key] = positions

        for key, og in sorted(black_groups.items(), key=lambda x: len(x[1]), reverse=True)[:4]:
            analyses, newly = await analyze_games_with_stockfish(
                og, depth=12, max_games=3, existing_db_rows=existing_db_rows
            )
            all_newly_analyzed.extend(newly)
            acpl, positions = aggregate_analysis(analyses)
            black_acpl_map[key] = acpl
            black_positions_map[key] = positions

        _save_new_game_rows(all_newly_analyzed, request.username)
        save_player_games([
            {"username": request.username.lower(), "game_id": g.game_id, "color": g.color}
            for g in games if g.game_id
        ])

        white_analyses = await batch_analyze_openings(
            opening_groups=white_groups,
            stats_map=white_stats_map,
            acpl_map=white_acpl_map,
            positions_map=white_positions_map,
            user_rating=user_rating,
            color="white",
        )
        black_analyses = await batch_analyze_openings(
            opening_groups=black_groups,
            stats_map=black_stats_map,
            acpl_map=black_acpl_map,
            positions_map=black_positions_map,
            user_rating=user_rating,
            color="black",
        )

        return AnalysisResponse(
            username=request.username,
            total_games=len(games),
            white_games=len(white_games),
            black_games=len(black_games),
            white_openings=[
                _build_opening_analysis(key, white_stats_map[key], white_analyses.get(key, {}),
                                        white_acpl_map.get(key, 0.0), white_positions_map.get(key, []))
                for key in sorted(white_groups.keys(), key=lambda k: white_stats_map[k].games, reverse=True)
            ],
            black_openings=[
                _build_opening_analysis(key, black_stats_map[key], black_analyses.get(key, {}),
                                        black_acpl_map.get(key, 0.0), black_positions_map.get(key, []))
                for key in sorted(black_groups.keys(), key=lambda k: black_stats_map[k].games, reverse=True)
            ],
            user_rating=user_rating,
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get("/history/{username}")
async def analysis_history(username: str):
    history = get_analysis_history(username)
    return {"username": username, "history": history}


@app.get("/trends/{username}")
async def opening_trends(username: str, opening: str, color: str = "white"):
    trends = get_opening_trends(username, opening, color)
    return {"username": username, "opening": opening, "color": color, "trends": trends}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_opening_analysis(
    key: str,
    stats: OpeningStats,
    analysis_dict: dict,
    acpl: float,
    positions: list[KeyPosition],
) -> OpeningAnalysis:
    verdict, verdict_color = determine_verdict(stats, acpl)
    return OpeningAnalysis(
        stats=stats,
        verdict=verdict,
        verdict_color=verdict_color,
        accuracy_summary=analysis_dict.get("accuracy_summary", ""),
        tactical_summary=analysis_dict.get("tactical_summary", ""),
        positional_summary=analysis_dict.get("positional_summary", ""),
        recommendation=analysis_dict.get("recommendation", ""),
        key_positions=positions,
        key_moments=analysis_dict.get("key_moments", []),
        resources=analysis_dict.get("resources", []),
        avg_centipawn_loss=acpl if acpl > 0 else None,
    )


def _build_basic_game_row(game, username: str) -> dict:
    """Build a games table row with just metadata (no Stockfish yet)."""
    username_lower = username.lower()
    white_player = username_lower if game.color == "white" else (game.opponent_name or "unknown").lower()
    black_player = username_lower if game.color == "black" else (game.opponent_name or "unknown").lower()
    return {
        "game_id": game.game_id,
        "white_player": white_player,
        "black_player": black_player,
        "result": game.result,
        "played_at": game.played_at,
        "time_control": game.time_control,
        "eco": game.eco,
        "opening_name": game.opening_name,
        "pgn": game.pgn,
        "moves": game.moves,
    }


def _save_new_game_rows(newly_analyzed: list[GameAnalysis], username: str) -> None:
    """Save Stockfish results for freshly analyzed games to stockfish_analysis table."""
    rows = []
    seen_ids: set[str] = set()

    for ga in newly_analyzed:
        g = ga.game
        if not g.game_id or g.game_id in seen_ids:
            continue
        seen_ids.add(g.game_id)

        rows.append({
            "game_id": g.game_id,
            "acpl_white": ga.acpl_white if ga.acpl_white > 0 else None,
            "acpl_black": ga.acpl_black if ga.acpl_black > 0 else None,
            "key_positions_white": [p.model_dump() for p in ga.key_positions_white],
            "key_positions_black": [p.model_dump() for p in ga.key_positions_black],
        })

    save_stockfish_analyses(rows)


def _row_to_game(row: dict, username: str, color: str) -> "Game":
    """Reconstruct a Game object from an all_games DB row."""
    username_lower = username.lower()
    if color == "white":
        opponent_name = row.get("black_player")
    else:
        opponent_name = row.get("white_player")
    # Don't use our own username as opponent name
    if opponent_name == username_lower:
        opponent_name = None
    return Game(
        pgn=row.get("pgn", ""),
        result=row.get("result", ""),
        color=color,
        opening_name=row.get("opening_name", ""),
        eco=row.get("eco", ""),
        opponent_name=opponent_name,
        opponent_rating=None,
        time_control=row.get("time_control"),
        moves=row.get("moves") or [],
        game_id=row.get("game_id", ""),
        played_at=row.get("played_at"),
    )


def _sse_event(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
