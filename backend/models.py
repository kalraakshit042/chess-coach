from pydantic import BaseModel
from typing import Optional


class Game(BaseModel):
    pgn: str
    result: str  # "1-0", "0-1", "1/2-1/2"
    color: str   # "white" or "black"
    opening_name: str
    eco: str
    opponent_rating: Optional[int] = None
    opponent_name: Optional[str] = None
    time_control: Optional[str] = None
    moves: list[str] = []
    game_id: str = ""
    played_at: Optional[str] = None  # ISO date string


class OpeningStats(BaseModel):
    name: str
    eco: str
    games: int
    wins: int
    draws: int
    losses: int
    avg_opponent_rating: Optional[float] = None

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games > 0 else 0.0

    @property
    def draw_rate(self) -> float:
        return self.draws / self.games if self.games > 0 else 0.0

    @property
    def loss_rate(self) -> float:
        return self.losses / self.games if self.games > 0 else 0.0


class KeyPosition(BaseModel):
    fen: str
    move_number: int
    comment: str
    eval_before: Optional[float] = None
    eval_after: Optional[float] = None
    best_move_san: Optional[str] = None      # Stockfish best move
    move_played_san: Optional[str] = None    # What the player actually played
    game_id: str = ""


class KeyMoment(BaseModel):
    """A specific position Claude wants to highlight, with full context for board rendering."""
    game_id: str
    game_url: str
    move_number: int
    fen: str
    move_played: str           # SAN of the move played
    better_move: Optional[str] = None  # SAN of Stockfish's suggestion
    explanation: str           # Claude's explanation of why this matters
    eval_swing: Optional[float] = None  # centipawns lost


class Resource(BaseModel):
    title: str
    url: str
    resource_type: str  # "lichess", "youtube", "book"


class OpeningAnalysis(BaseModel):
    stats: OpeningStats
    verdict: str        # "Strong", "Needs Work", "Weak"
    verdict_color: str  # "green", "yellow", "red"
    accuracy_summary: str
    tactical_summary: str
    positional_summary: str
    recommendation: str
    key_positions: list[KeyPosition] = []   # from Stockfish (for fallback display)
    key_moments: list[KeyMoment] = []       # from Claude (richer, with explanations)
    resources: list[Resource] = []
    avg_centipawn_loss: Optional[float] = None


class AnalysisResponse(BaseModel):
    username: str
    total_games: int
    white_games: int
    black_games: int
    white_openings: list[OpeningAnalysis]
    black_openings: list[OpeningAnalysis]
    user_rating: Optional[int] = None


class AnalyzeRequest(BaseModel):
    username: str
    months: int = 12
    speed: str = "all"  # "all", "rapid", "blitz", "bullet"
    test_mode: bool = False  # if True, cap at 10 games
