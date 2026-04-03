import unittest
from unittest.mock import MagicMock
from datetime import date
from src.core.game_runner import GameRunner
from src.core.season import Season, SeasonScore
from data.readers.question import Question


class TestGameRunnerFormatAnswer(unittest.TestCase):
    def setUp(self):
        self.mock_qs = MagicMock()
        self.mock_dm = MagicMock()
        self.runner = GameRunner(self.mock_qs, self.mock_dm)
        self.runner.daily_question_id = 123
        self.question = Question("Q", "Main Answer", "C", 100)

    def test_format_answer_no_alts(self):
        self.mock_dm.get_alternative_answers.return_value = []
        result = self.runner.format_answer(self.question)
        self.assertIn("Main Answer", result)
        self.assertNotIn("Also accepted", result)

    def test_format_answer_with_alts(self):
        self.mock_dm.get_alternative_answers.return_value = ["Alt1", "Alt2"]
        result = self.runner.format_answer(self.question)
        self.assertIn("Main Answer", result)
        self.assertIn("Also accepted", result)
        self.assertIn("Alt1", result)
        self.assertIn("Alt2", result)


class TestGetActiveLeaderboard(unittest.TestCase):
    """Tests for GameRunner.get_active_leaderboard season-awareness."""

    def setUp(self):
        self.mock_qs = MagicMock()
        self.mock_dm = MagicMock()
        self.runner = GameRunner(self.mock_qs, self.mock_dm)
        self.runner.config = MagicMock()
        self.runner.config.get.return_value = "🔥"

    def _make_season(self):
        return Season(1, "March 2026", date(2026, 3, 1), date(2026, 3, 31), True)

    def test_seasons_disabled_calls_all_time(self):
        """When seasons are disabled, get_active_leaderboard returns all-time leaderboard."""
        self.runner.season_manager = MagicMock()
        self.runner.season_manager.enabled = False
        self.runner.get_scores_leaderboard = MagicMock(return_value="All-Time LB")

        result = self.runner.get_active_leaderboard(guild=None)

        self.assertEqual(result, "All-Time LB")
        self.runner.season_manager.get_or_create_current_season.assert_not_called()

    def test_seasons_enabled_with_active_season_returns_season_lb(self):
        """When seasons are enabled and a season exists, returns formatted season leaderboard."""
        season = self._make_season()
        self.runner.season_manager = MagicMock()
        self.runner.season_manager.enabled = True
        self.runner.season_manager.get_or_create_current_season.return_value = season
        self.runner.season_manager.get_season_progress.return_value = (2, 31)
        score = MagicMock(spec=SeasonScore)
        score.player_id = "p1"
        score.points = 150
        score.current_streak = 3
        self.runner.season_manager.get_season_leaderboard.return_value = [
            (score, "Alice")
        ]
        self.runner.get_scores_leaderboard = MagicMock()

        result = self.runner.get_active_leaderboard(guild=None)

        self.assertIn("March 2026", result)
        self.assertIn("Alice", result)
        self.assertIn("150", result)
        self.runner.get_scores_leaderboard.assert_not_called()

    def test_seasons_enabled_no_active_season_falls_back_to_all_time(self):
        """When seasons are enabled but no season exists, falls back to all-time."""
        self.runner.season_manager = MagicMock()
        self.runner.season_manager.enabled = True
        self.runner.season_manager.get_or_create_current_season.return_value = None
        self.runner.get_scores_leaderboard = MagicMock(return_value="All-Time LB")

        result = self.runner.get_active_leaderboard(guild=None)

        self.assertEqual(result, "All-Time LB")
        self.runner.get_scores_leaderboard.assert_called_once()

    def test_season_leaderboard_header_contains_day_progress(self):
        """Season leaderboard header shows current day and total days."""
        season = self._make_season()
        self.runner.season_manager = MagicMock()
        self.runner.season_manager.enabled = True
        self.runner.season_manager.get_or_create_current_season.return_value = season
        self.runner.season_manager.get_season_progress.return_value = (2, 31)
        self.runner.season_manager.get_season_leaderboard.return_value = []

        result = self.runner.get_active_leaderboard()

        self.assertIn("Day 2/31", result)

    def test_season_leaderboard_no_scores_message(self):
        """When the season exists but has no scores, returns appropriate message."""
        season = self._make_season()
        self.runner.season_manager = MagicMock()
        self.runner.season_manager.enabled = True
        self.runner.season_manager.get_or_create_current_season.return_value = season
        self.runner.season_manager.get_season_progress.return_value = (1, 31)
        self.runner.season_manager.get_season_leaderboard.return_value = []

        result = self.runner.get_active_leaderboard()

        self.assertIn("No scores this season yet", result)
