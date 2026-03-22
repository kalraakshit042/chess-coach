"""
Claude API integration for chess coaching.
Two-phase:
  1. generate_opening_knowledge() — one-time per ECO+color, cached in DB
  2. coach_opening() — per-user, uses cached knowledge + player Stockfish data
"""
import asyncio
import json
import os
from typing import Optional

import anthropic

import re

from models import (
    CoachingInsight, Game, KeyMoment, KeyPosition,
    OpeningAnalysis, OpeningStats, Resource, StudyPlan,
)
from resources import get_resources_for_opening

LICHESS_GAME_BASE = "https://lichess.org"

# Matches standard SAN piece moves (Nf3, Bb5, Rxe5, Qxd4) and pawn captures (exd5, fxg6)
# Excludes bare pawn pushes (e4, d5) which are too ambiguous in plain text
_SAN_RE = re.compile(
    r'(?<![a-zA-Z])([KQRBN][a-h1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?'
    r'|[a-h]x[a-h][1-8](?:=[QRBN])?[+#]?)(?![a-zA-Z0-9])'
)

MODEL = "claude-sonnet-4-20250514"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0

LICHESS_GAME_BASE = "https://lichess.org"


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set.")
    return anthropic.Anthropic(api_key=api_key)


def _build_system_prompt(user_rating: Optional[int]) -> str:
    rating_str = f"around {user_rating}" if user_rating else "between 1200-1800"
    return (
        f"You are an expert chess coach rated 2500+. You are analyzing games for a player "
        f"rated {rating_str}. Your coaching is specific, concrete, and references exact moves. "
        "When you cite a game, always use the game ID provided so it can be linked. "
        "When you identify a mistake, always explain what the better move was AND why. "
        "Never say 'Game 1' or 'Game 2' — always reference by game ID and opponent. "
        "Keep text summaries to 2-3 sentences each. Be direct."
    )


def _format_games_for_prompt(games: list[Game], max_games: int = 5) -> str:
    """Format game samples with IDs, opponents, dates and results."""
    sample = games[:max_games]
    parts = []
    for g in sample:
        result_label = (
            "Win" if (g.result == "1-0" and g.color == "white") or
                      (g.result == "0-1" and g.color == "black")
            else "Draw" if g.result == "1/2-1/2"
            else "Loss"
        )
        opp = f"vs {g.opponent_name}" if g.opponent_name else ""
        rating = f"({g.opponent_rating})" if g.opponent_rating else ""
        date = f"on {g.played_at}" if g.played_at else ""
        moves_preview = " ".join(g.moves[:30])
        game_url = f"{LICHESS_GAME_BASE}/{g.game_id}" if g.game_id else "unknown"
        parts.append(
            f"[ID:{g.game_id}] {result_label} {opp}{rating} {date} | URL:{game_url}\n"
            f"  Moves: {moves_preview}" + (" ..." if len(g.moves) > 30 else "")
        )
    return "\n".join(parts)


def _format_key_positions(positions: list[KeyPosition]) -> str:
    """Format Stockfish-computed key positions for the prompt."""
    if not positions:
        return "No engine key positions available."
    lines = []
    for p in positions:
        game_url = f"{LICHESS_GAME_BASE}/{p.game_id}" if p.game_id else "unknown"
        better = f"Better move: {p.best_move_san}" if p.best_move_san else "Better move: unknown"
        played = f"Played: {p.move_played_san}" if p.move_played_san else ""
        swing = abs((p.eval_after or 0) - (p.eval_before or 0)) / 100
        lines.append(
            f"[ID:{p.game_id}] Move {p.move_number} | {played} | {better} | "
            f"Eval swing: {swing:.1f} pawns\n"
            f"  FEN: {p.fen}"
        )
    return "\n".join(lines)


def _format_resources(resources: list[Resource]) -> str:
    if not resources:
        return "No specific resources found."
    return "\n".join(
        f"- [{r.resource_type.upper()}] {r.title}: {r.url}"
        for r in resources
    )


def _format_eval_summary(avg_acpl: float) -> str:
    if avg_acpl <= 0:
        return "No engine accuracy data available."
    label = (
        "Excellent (grandmaster-level)" if avg_acpl < 30 else
        "Good (club player level)" if avg_acpl < 50 else
        "Average — room for improvement" if avg_acpl < 80 else
        "Below average — significant inaccuracies present"
    )
    return f"Average Centipawn Loss (ACPL): {avg_acpl:.1f} — {label}"


def build_move_index(game_analyses: list) -> dict[str, str]:
    """
    Build {move_san: game_id} from all games' move lists.
    First game wins — used to hyperlink move mentions back to real games.
    """
    index: dict[str, str] = {}
    for ga in game_analyses:
        for move in (ga.game.moves or []):
            clean = move.rstrip('+#')   # strip check/mate symbols for matching
            if clean not in index:
                index[clean] = ga.game.game_id
    return index


def annotate_moves(text: str, move_index: dict[str, str]) -> str:
    """
    Replace verified SAN move mentions with [move](lichess_url).
    Unverified moves (Claude hallucinated / opening theory) are left as plain text.
    """
    def replace(m: re.Match) -> str:
        raw = m.group(1)
        clean = raw.rstrip('+#')
        game_id = move_index.get(clean)
        if game_id:
            return f"[{raw}]({LICHESS_GAME_BASE}/{game_id})"
        return raw  # not found in user's games — leave unlinked

    return _SAN_RE.sub(replace, text)


def _parse_json_response(text: str) -> dict:
    """Strip markdown fences and parse JSON."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text)


async def generate_opening_knowledge(opening_name: str, eco: str, color: str) -> dict:
    """
    One-time generation of opening theory knowledge for a specific ECO + color.
    Cached in Supabase — only called when missing from DB.
    Returns dict: {strategic_goal, key_plans, transition_point, tactical_themes, common_mistakes}
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    prompt = f"""You are a chess expert. Generate a concise opening knowledge guide for:
Opening: {opening_name} ({eco}), played as {color}.

Return ONLY a JSON object with these exact fields:
{{
  "strategic_goal": "What this side is trying to achieve — 2 sentences covering main ideas and pawn structure goals",
  "key_plans": ["plan 1", "plan 2", "plan 3"],
  "transition_point": "At what move / position does opening theory typically end and the middlegame begin — 1-2 sentences",
  "tactical_themes": ["theme 1", "theme 2"],
  "common_mistakes": ["most common mistake 1", "most common mistake 2", "most common mistake 3"]
}}

Be specific to this exact opening. Name concrete moves and squares where relevant."""

    for attempt in range(MAX_RETRIES):
        try:
            resp = await asyncio.to_thread(
                client.messages.create,
                model=MODEL,
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            return _parse_json_response(resp.content[0].text)
        except Exception:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))

    # Minimal fallback so the flow never breaks
    return {
        "strategic_goal": f"Understand the key ideas of the {opening_name} as {color}.",
        "key_plans": ["Control the center", "Develop pieces", "Castle to safety"],
        "transition_point": "Opening theory typically ends around move 10-15.",
        "tactical_themes": ["Pin", "Fork"],
        "common_mistakes": ["Premature pawn advances", "Ignoring opponent threats"],
    }


async def coach_opening(
    opening_name: str,
    eco: str,
    color: str,
    knowledge: dict,
    diagnosis,          # CoachingDiagnosis
    avg_acpl: Optional[float],
    games_analysed: int,
) -> CoachingInsight:
    """
    Per-user coaching using cached opening knowledge + Stockfish diagnosis.
    Returns structured CoachingInsight with 4 categories.
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    # Format opening knowledge
    key_plans = "\n".join(f"  - {p}" for p in (knowledge.get("key_plans") or []))
    common_mistakes = "\n".join(f"  - {m}" for m in (knowledge.get("common_mistakes") or []))
    tactical_themes = ", ".join(knowledge.get("tactical_themes") or [])

    # Format critical position
    cp = diagnosis.critical_position
    if cp:
        swing_pawns = abs((cp.eval_after or 0) - (cp.eval_before or 0)) / 100
        critical_text = (
            f"FEN: {cp.fen}\n"
            f"Played: {cp.move_played_san} (eval {cp.eval_before/100:.1f} → {cp.eval_after/100:.1f} pawns, lost {swing_pawns:.1f} pawns)\n"
            f"Stockfish best: {cp.best_move_san or 'unknown'}"
        )
    else:
        critical_text = "No critical position identified."

    prompt = f"""You are an expert chess coach (2500+ rated). Analyse this player's performance.
Address the player directly as "you" throughout. Never say "the player".

[OPENING KNOWLEDGE: {opening_name} ({eco}) as {color}]
Strategic goal: {knowledge.get('strategic_goal', '')}
Key plans:
{key_plans}
Theory ends: {knowledge.get('transition_point', '')}
Tactical themes: {tactical_themes}
Common mistakes in this opening:
{common_mistakes}

[THIS PLAYER'S DATA]
Games analysed: {games_analysed}
Record: {diagnosis.wins}W / {diagnosis.draws}D / {diagnosis.losses}L
Average ACPL: {avg_acpl or 'N/A'}
Mistake pattern: {diagnosis.outcome_type} — problems cluster in the {diagnosis.dominant_phase} (avg move {diagnosis.avg_mistake_move or '?'})
Win ACPL: {diagnosis.win_avg_acpl or 'N/A'} | Loss ACPL: {diagnosis.loss_avg_acpl or 'N/A'}

[WORST POSITION ACROSS ALL GAMES]
{critical_text}

IMPORTANT: Do NOT restate any numbers (ACPL, blunder counts, win rates). Those are already shown. Focus entirely on chess — strategy, piece placement, pawn structure, specific moves and squares. Be a coach, not a calculator.

Return ONLY a JSON object with these exact fields:
{{
  "whats_wrong": "2-3 sentences in chess terms only — no numbers. Reference the opening's strategic goals and where this player deviates. Name specific moves, squares, or pieces.",
  "critical_moment": "2-3 sentences. Explain the worst position: why the played move loses, what the best move achieves, what chess concept this illustrates.",
  "pattern": "2 sentences. Name the underlying chess weakness — calculation depth, structural misunderstanding, theory gap, or piece coordination. Be precise.",
  "study_plan": {{
    "focus": "tactics OR opening_theory OR positional OR endgame",
    "title": "Specific study topic title (e.g. 'Nd5 sacrifice patterns in open games')",
    "action": "One concrete, immediate action — specific line, puzzle theme, concept, or game to study",
    "lichess_hint": "Lichess puzzle theme name or study search term (e.g. 'discoveredAttack' or 'Danish Gambit plans')"
  }}
}}"""

    for attempt in range(MAX_RETRIES):
        try:
            resp = await asyncio.to_thread(
                client.messages.create,
                model=MODEL,
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}],
            )
            parsed = _parse_json_response(resp.content[0].text)
            sp = parsed.get("study_plan", {})
            return CoachingInsight(
                whats_wrong=parsed.get("whats_wrong", ""),
                critical_moment=parsed.get("critical_moment") or None,
                pattern=parsed.get("pattern", ""),
                study_plan=StudyPlan(
                    focus=sp.get("focus", "positional"),
                    title=sp.get("title", ""),
                    action=sp.get("action", ""),
                    lichess_hint=sp.get("lichess_hint") or None,
                ),
            )
        except Exception:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))

    # Fallback
    return CoachingInsight(
        whats_wrong=f"Unable to generate coaching for {opening_name} at this time.",
        critical_moment=None,
        pattern="Review your games manually to identify recurring patterns.",
        study_plan=StudyPlan(
            focus=diagnosis.outcome_type,
            title=f"Study {opening_name} plans",
            action=f"Play through master games in the {opening_name} as {color}.",
            lichess_hint=opening_name,
        ),
    )


async def analyze_opening(
    opening_name: str,
    eco: str,
    games: list[Game],
    stats: OpeningStats,
    avg_acpl: float,
    key_positions: list[KeyPosition],
    user_rating: Optional[int],
    color: str,
    resources: list[Resource],
) -> dict:
    """
    Use Claude to generate structured coaching analysis for an opening.
    Returns dict with text summaries + key_moments list.
    """
    client = _get_client()

    win_rate = int(stats.wins / stats.games * 100) if stats.games > 0 else 0
    avg_opp = f"~{stats.avg_opponent_rating:.0f}" if stats.avg_opponent_rating else "unknown"

    games_text = _format_games_for_prompt(games)
    positions_text = _format_key_positions(key_positions)
    resources_text = _format_resources(resources)
    eval_text = _format_eval_summary(avg_acpl)

    prompt = f"""Analyze this player's performance in the **{opening_name}** ({eco}) as {color}.

**Statistics:**
- Games: {stats.games} | Results: {stats.wins}W/{stats.draws}D/{stats.losses}L ({win_rate}% win rate)
- Avg opponent rating: {avg_opp}
- {eval_text}

**Game samples (reference by ID when citing):**
{games_text}

**Engine-identified key positions (use these FENs in key_moments — do NOT invent FENs):**
{positions_text}

**Available study resources:**
{resources_text}

Respond with ONLY a JSON object in this exact format:
{{
  "accuracy_summary": "2-3 sentences. Reference a specific game by ID and opponent name if citing an example. Mention ACPL. Explain what move was wrong and what was better.",
  "tactical_summary": "2-3 sentences. Reference a specific game ID and opponent if citing a tactical miss. Name the exact move/threat missed.",
  "positional_summary": "2-3 sentences. Identify a recurring positional pattern across multiple games. Be specific about the weakness (e.g. 'd5 square weak', 'premature pawn advances').",
  "recommendation": "One concrete, actionable recommendation. Reference a specific position or move order. Tell the player exactly what to do differently in their next game.",
  "key_moments": [
    {{
      "game_id": "<use a game ID from above>",
      "game_url": "<the URL from above>",
      "move_number": <integer>,
      "fen": "<copy exactly from the engine positions above — do not invent>",
      "move_played": "<SAN of move played>",
      "better_move": "<SAN of better move, or null>",
      "explanation": "1-2 sentences: why move_played was wrong, why better_move is correct.",
      "eval_swing": <centipawns lost as a number, or null>
    }}
  ],
  "resources": [
    {{"title": "<title>", "url": "<url>", "resource_type": "<lichess|youtube|book>"}}
  ]
}}

Rules:
- key_moments: include 1-3 items, ONLY from the engine positions listed above. If no engine positions available, use an empty array [].
- resources: include 1-2 of the most relevant resources from the list above.
- All FENs must be copied exactly from the engine positions — never hallucinate a FEN.
- game_url must come from the game samples above."""

    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1000,
                system=_build_system_prompt(user_rating),
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text.strip()

            # Strip markdown code block if present
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            parsed = json.loads(content)

            # Build KeyMoment objects
            key_moments: list[KeyMoment] = []
            for km in parsed.get("key_moments", []):
                try:
                    key_moments.append(KeyMoment(
                        game_id=km.get("game_id", ""),
                        game_url=km.get("game_url", ""),
                        move_number=int(km.get("move_number", 0)),
                        fen=km.get("fen", ""),
                        move_played=km.get("move_played", ""),
                        better_move=km.get("better_move") or None,
                        explanation=km.get("explanation", ""),
                        eval_swing=km.get("eval_swing"),
                    ))
                except Exception:
                    continue

            # Build Resource objects
            parsed_resources: list[Resource] = []
            for r in parsed.get("resources", []):
                try:
                    parsed_resources.append(Resource(
                        title=r.get("title", ""),
                        url=r.get("url", ""),
                        resource_type=r.get("resource_type", "lichess"),
                    ))
                except Exception:
                    continue

            # Fallback: use our DB resources if Claude returned none
            if not parsed_resources:
                parsed_resources = resources

            return {
                "accuracy_summary": parsed.get("accuracy_summary", ""),
                "tactical_summary": parsed.get("tactical_summary", ""),
                "positional_summary": parsed.get("positional_summary", ""),
                "recommendation": parsed.get("recommendation", ""),
                "key_moments": key_moments,
                "resources": parsed_resources,
            }

        except anthropic.RateLimitError:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))
            else:
                return _fallback_analysis(stats, avg_acpl, opening_name, color, resources)

        except Exception:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_BASE_DELAY)
            else:
                return _fallback_analysis(stats, avg_acpl, opening_name, color, resources)

    return _fallback_analysis(stats, avg_acpl, opening_name, color, resources)


def _fallback_analysis(
    stats: OpeningStats,
    avg_acpl: float,
    opening_name: str,
    color: str,
    resources: list[Resource],
) -> dict:
    acpl_note = f" Your ACPL is {avg_acpl:.0f}." if avg_acpl > 0 else ""
    return {
        "accuracy_summary": f"Analysis unavailable.{acpl_note} Review your games manually for accuracy issues.",
        "tactical_summary": "Review tactical patterns common in this opening.",
        "positional_summary": f"Study the key positional ideas of the {opening_name}.",
        "recommendation": f"Play through master games in the {opening_name} as {color} to understand typical plans.",
        "key_moments": [],
        "resources": resources,
    }


def _mock_opening_analysis(opening_groups: dict) -> dict:
    """Return instant fake analysis — used when MOCK_CLAUDE=true."""
    return {
        key: {
            "accuracy_summary": "[MOCK] Accuracy summary placeholder.",
            "tactical_summary": "[MOCK] Tactical summary placeholder.",
            "positional_summary": "[MOCK] Positional summary placeholder.",
            "recommendation": "[MOCK] Work on this opening.",
            "key_moments": [],
            "resources": [],
        }
        for key in opening_groups
    }


async def batch_analyze_openings(
    opening_groups: dict[str, list[Game]],
    stats_map: dict[str, OpeningStats],
    acpl_map: dict[str, float],
    positions_map: dict[str, list[KeyPosition]],
    user_rating: Optional[int],
    color: str,
    progress_callback=None,
) -> dict[str, dict]:
    if os.environ.get("MOCK_CLAUDE") == "true":
        return _mock_opening_analysis(opening_groups)

    results = {}
    opening_keys = list(opening_groups.keys())

    for i, key in enumerate(opening_keys):
        games = opening_groups[key]
        stats = stats_map[key]
        avg_acpl = acpl_map.get(key, 0.0)
        key_positions = positions_map.get(key, [])
        resources = get_resources_for_opening(stats.eco, stats.name)

        analysis = await analyze_opening(
            opening_name=stats.name,
            eco=stats.eco,
            games=games,
            stats=stats,
            avg_acpl=avg_acpl,
            key_positions=key_positions,
            user_rating=user_rating,
            color=color,
            resources=resources,
        )
        results[key] = analysis

        if progress_callback:
            await progress_callback(i + 1, len(opening_keys))

        if i < len(opening_keys) - 1:
            await asyncio.sleep(0.5)

    return results
