"""Tests for analysis.py — Stockfish path detection and game analysis logic."""
from unittest.mock import patch
from analysis import find_stockfish, STOCKFISH_PATHS, compute_opening_stats
from models import Game


class TestFindStockfish:
    def test_returns_none_when_no_stockfish_installed(self):
        with patch("os.path.isfile", return_value=False), \
             patch("shutil.which", return_value=None):
            assert find_stockfish() is None

    def test_returns_first_matching_path(self):
        def fake_isfile(p):
            return p == "/usr/local/bin/stockfish"
        with patch("os.path.isfile", side_effect=fake_isfile), \
             patch("os.access", return_value=True):
            result = find_stockfish()
            assert result == "/usr/local/bin/stockfish"

    def test_falls_back_to_shutil_which(self):
        with patch("os.path.isfile", return_value=False), \
             patch("shutil.which", return_value="/nix/store/xxx/bin/stockfish"):
            assert find_stockfish() == "/nix/store/xxx/bin/stockfish"


class TestComputeOpeningStats:
    def _make_game(self, result, color="white", eco="B10", name="Caro-Kann"):
        return Game(
            pgn="1. e4 c6",
            result=result,
            color=color,
            opening_name=name,
            eco=eco,
            opponent_name="opponent",
            opponent_rating=1500,
            moves=["e4", "c6"],
            game_id="test123",
        )

    def test_counts_wins_draws_losses(self):
        games = [
            self._make_game("1-0"),
            self._make_game("1-0"),
            self._make_game("0-1"),
            self._make_game("1/2-1/2"),
        ]
        stats = compute_opening_stats(games)
        assert stats.games == 4
        assert stats.wins == 2
        assert stats.draws == 1
        assert stats.losses == 1

    def test_computes_win_rate(self):
        games = [self._make_game("1-0"), self._make_game("0-1")]
        stats = compute_opening_stats(games)
        assert stats.win_rate == 0.5
