"""
FastAPI backend for Chess Coach.
Fetches Lichess games, runs Stockfish analysis, and generates coaching with Claude.
"""
import asyncio
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import json

load_dotenv()

from analysis import (
    aggregate_analysis,
    analyze_games_with_stockfish,
    compute_opening_stats,
    determine_verdict,
)
from claude_coach import batch_analyze_openings
from database import (
    compute_games_hash,
    get_cached_analysis,
    save_analysis,
    get_game_analyses_batch,
    save_game_analyses_batch,
    get_analysis_history,
    get_opening_trends,
)
from lichess import fetch_user_games, group_games_by_opening
from models import (
    AnalyzeRequest,
    AnalysisResponse,
    KeyPosition,
    OpeningAnalysis,
    OpeningStats,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Chess Coach API",
    description="AI-powered chess coaching using Lichess game history and Claude.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/analyze/stream")
async def analyze_stream(request: AnalyzeRequest):
    """
    Stream analysis progress as Server-Sent Events (SSE).
    Yields JSON progress updates, then the final result.
    """
    async def event_generator():
        try:
            # Step 1: Fetch games
            yield _sse_event("progress", {"step": "fetching", "message": f"Fetching games for {request.username} from Lichess..."})

            games, user_rating = await fetch_user_games(
                request.username, months=request.months, speed=request.speed
            )

            if request.test_mode:
                games = games[:20]

            if not games:
                speed_label = f" ({request.speed})" if request.speed != "all" else ""
                yield _sse_event("error", {"message": f"No rated games found for '{request.username}' in the last {request.months} months{speed_label}."})
                return

            # Level 2 cache check — keyed by the actual set of games
            game_ids = [g.game_id for g in games if g.game_id]
            games_hash = compute_games_hash(game_ids)
            cached = get_cached_analysis(games_hash)
            if cached:
                yield _sse_event("progress", {"step": "fetching", "message": f"Found cached analysis for these {len(games)} games. Loading instantly..."})
                yield _sse_event("complete", {**cached, "from_cache": True})
                return

            white_games = [g for g in games if g.color == "white"]
            black_games = [g for g in games if g.color == "black"]

            yield _sse_event("progress", {
                "step": "games_fetched",
                "message": f"Found {len(games)} games ({len(white_games)} as white, {len(black_games)} as black). Grouping openings...",
                "total_games": len(games),
                "white_games": len(white_games),
                "black_games": len(black_games),
            })

            # Step 2: Group by opening
            white_groups = group_games_by_opening(white_games, min_games=3)
            black_groups = group_games_by_opening(black_games, min_games=3)

            total_openings = len(white_groups) + len(black_groups)
            yield _sse_event("progress", {
                "step": "openings_grouped",
                "message": f"Found {len(white_groups)} white openings and {len(black_groups)} black openings with 3+ games. Running engine analysis...",
                "white_openings_count": len(white_groups),
                "black_openings_count": len(black_groups),
            })

            # Step 3: Stockfish analysis — Level 1 cache per game_id
            white_stats_map = {k: compute_opening_stats(v) for k, v in white_groups.items()}
            black_stats_map = {k: compute_opening_stats(v) for k, v in black_groups.items()}

            white_acpl_map: dict[str, float] = {}
            white_positions_map: dict[str, list[KeyPosition]] = {}
            black_acpl_map: dict[str, float] = {}
            black_positions_map: dict[str, list[KeyPosition]] = {}

            # Load Level 1 cache for all games at once
            all_game_ids = [g.game_id for g in games if g.game_id]
            cached_game_analyses = get_game_analyses_batch(all_game_ids)
            all_new_cache_rows: list[dict] = []

            sorted_white = sorted(white_groups.items(), key=lambda x: len(x[1]), reverse=True)
            sorted_black = sorted(black_groups.items(), key=lambda x: len(x[1]), reverse=True)
            engine_openings_limit = 4

            for key, og in sorted_white[:engine_openings_limit]:
                cached_count = sum(1 for g in og if g.game_id in cached_game_analyses)
                yield _sse_event("progress", {
                    "step": "engine_analysis",
                    "message": f"Evaluating white opening: {white_stats_map[key].name} ({cached_count}/{min(len(og),3)} games cached)...",
                })
                analyses, new_rows = await analyze_games_with_stockfish(
                    og, depth=12, max_games=3, cached_game_analyses=cached_game_analyses
                )
                all_new_cache_rows.extend(new_rows)
                acpl, positions = aggregate_analysis(analyses)
                white_acpl_map[key] = acpl
                white_positions_map[key] = positions

            for key, og in sorted_black[:engine_openings_limit]:
                cached_count = sum(1 for g in og if g.game_id in cached_game_analyses)
                yield _sse_event("progress", {
                    "step": "engine_analysis",
                    "message": f"Evaluating black opening: {black_stats_map[key].name} ({cached_count}/{min(len(og),3)} games cached)...",
                })
                analyses, new_rows = await analyze_games_with_stockfish(
                    og, depth=12, max_games=3, cached_game_analyses=cached_game_analyses
                )
                all_new_cache_rows.extend(new_rows)
                acpl, positions = aggregate_analysis(analyses)
                black_acpl_map[key] = acpl
                black_positions_map[key] = positions

            # Persist new Level 1 cache rows
            if all_new_cache_rows:
                save_game_analyses_batch(all_new_cache_rows)

            # Step 4: Claude analysis
            analyzed_count = [0]
            total_to_analyze = total_openings

            yield _sse_event("progress", {
                "step": "claude_analysis",
                "message": f"Generating AI coaching for {total_openings} openings...",
                "total_openings": total_openings,
            })

            async def white_progress(done, total):
                yield  # no-op, handled below

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
                "message": f"White openings analyzed. Working on black openings...",
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
            def build_opening_analysis(
                key: str,
                games_list,
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

            white_opening_analyses = [
                build_opening_analysis(
                    key,
                    white_groups[key],
                    white_stats_map[key],
                    white_analyses.get(key, {}),
                    white_acpl_map.get(key, 0.0),
                    white_positions_map.get(key, []),
                )
                for key in sorted(white_groups.keys(), key=lambda k: white_stats_map[k].games, reverse=True)
            ]

            black_opening_analyses = [
                build_opening_analysis(
                    key,
                    black_groups[key],
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
    """
    Non-streaming analysis endpoint. Fetches games, runs analysis, returns full result.
    Use /analyze/stream for progress updates.
    """
    try:
        games, user_rating = await fetch_user_games(
            request.username, months=request.months, speed=request.speed
        )

        if not games:
            raise HTTPException(
                status_code=404,
                detail=f"No rated games found for '{request.username}' in the last {request.months} months.",
            )

        white_games = [g for g in games if g.color == "white"]
        black_games = [g for g in games if g.color == "black"]

        white_groups = group_games_by_opening(white_games, min_games=3)
        black_groups = group_games_by_opening(black_games, min_games=3)

        white_stats_map = {k: compute_opening_stats(v) for k, v in white_groups.items()}
        black_stats_map = {k: compute_opening_stats(v) for k, v in black_groups.items()}

        white_acpl_map: dict[str, float] = {}
        white_positions_map: dict[str, list[KeyPosition]] = {}
        black_acpl_map: dict[str, float] = {}
        black_positions_map: dict[str, list[KeyPosition]] = {}

        sorted_white = sorted(white_groups.items(), key=lambda x: len(x[1]), reverse=True)
        sorted_black = sorted(black_groups.items(), key=lambda x: len(x[1]), reverse=True)

        for key, og in sorted_white[:4]:
            analyses = await analyze_games_with_stockfish(og, depth=12, max_games=3)
            acpl, positions = aggregate_analysis(analyses)
            white_acpl_map[key] = acpl
            white_positions_map[key] = positions

        for key, og in sorted_black[:4]:
            analyses = await analyze_games_with_stockfish(og, depth=12, max_games=3)
            acpl, positions = aggregate_analysis(analyses)
            black_acpl_map[key] = acpl
            black_positions_map[key] = positions

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

        def build_opening_analysis(key, stats, analysis_dict, acpl, positions):
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

        white_opening_analyses = [
            build_opening_analysis(
                key,
                white_stats_map[key],
                white_analyses.get(key, {}),
                white_acpl_map.get(key, 0.0),
                white_positions_map.get(key, []),
            )
            for key in sorted(white_groups.keys(), key=lambda k: white_stats_map[k].games, reverse=True)
        ]

        black_opening_analyses = [
            build_opening_analysis(
                key,
                black_stats_map[key],
                black_analyses.get(key, {}),
                black_acpl_map.get(key, 0.0),
                black_positions_map.get(key, []),
            )
            for key in sorted(black_groups.keys(), key=lambda k: black_stats_map[k].games, reverse=True)
        ]

        return AnalysisResponse(
            username=request.username,
            total_games=len(games),
            white_games=len(white_games),
            black_games=len(black_games),
            white_openings=white_opening_analyses,
            black_openings=black_opening_analyses,
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
    """Return past analysis metadata for a user (most recent first)."""
    history = get_analysis_history(username)
    return {"username": username, "history": history}


@app.get("/trends/{username}")
async def opening_trends(username: str, opening: str, color: str = "white"):
    """Return win rate and ACPL trend for a specific opening over time."""
    trends = get_opening_trends(username, opening, color)
    return {"username": username, "opening": opening, "color": color, "trends": trends}


def _sse_event(event_type: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
