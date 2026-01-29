"""
Unit tests for SeasonManager.
"""

import unittest
from unittest.mock import MagicMock, patch, call
from datetime import date, datetime
from src.core.season_manager import SeasonManager
from src.core.data_manager import DataManager
from src.cfg.main import ConfigReader
from src.core.season import Season, SeasonScore


class TestSeasonManager(unittest.TestCase):
    """Test SeasonManager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_data_manager = MagicMock(spec=DataManager)
        self.mock_config = MagicMock(spec=ConfigReader)

        # Default config values
        self.mock_config.get_season_mode.return_value = "calendar"
        self.mock_config.get_season_duration_days.return_value = 30
        self.mock_config.get_season_auto_create.return_value = True
        self.mock_config.get_season_trophy_positions.return_value = 3

        self.manager = SeasonManager(self.mock_data_manager, self.mock_config)

    def test_get_or_create_current_season_active_exists(self):
        """Test getting current season when one exists."""
        active_season = Season(
            1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True
        )
        self.mock_data_manager.get_current_season.return_value = active_season

        result = self.manager.get_or_create_current_season()

        self.assertEqual(result, active_season)
        self.mock_data_manager.get_current_season.assert_called_once()
        self.mock_data_manager.create_season.assert_not_called()

    def test_get_or_create_current_season_no_season(self):
        """Test creating new season when none exists."""
        self.mock_data_manager.get_current_season.return_value = None
        new_season = Season(
            1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True
        )
        self.mock_data_manager.get_season_by_id.return_value = new_season

        with patch("src.core.season_manager.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 15)
            result = self.manager.get_or_create_current_season()

        self.assertEqual(result, new_season)
        self.mock_data_manager.create_season.assert_called_once()

    def test_get_or_create_current_season_expired(self):
        """Test handling expired season."""
        expired_season = Season(
            1, "December 2025", date(2025, 12, 1), date(2025, 12, 31), True
        )
        self.mock_data_manager.get_current_season.return_value = expired_season
        new_season = Season(
            2, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True
        )
        self.mock_data_manager.get_season_by_id.return_value = new_season

        with patch("src.core.season_manager.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 15)
            result = self.manager.get_or_create_current_season()

        # Should create new season
        self.mock_data_manager.create_season.assert_called_once()

    def test_check_season_transition_same_month(self):
        """Test check_season_transition when still in same month."""
        current_season = Season(
            1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True
        )
        self.mock_data_manager.get_current_season.return_value = current_season

        with patch("src.core.season_manager.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 15)
            result = self.manager.check_season_transition()

        self.assertFalse(result)
        self.mock_data_manager.end_season.assert_not_called()

    def test_check_season_transition_new_month(self):
        """Test check_season_transition at month boundary."""
        current_season = Season(
            1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True
        )
        self.mock_data_manager.get_current_season.return_value = current_season
        new_season = Season(
            2, "February 2026", date(2026, 2, 1), date(2026, 2, 28), True
        )
        self.mock_data_manager.get_season_by_id.return_value = new_season

        result = self.manager.check_season_transition(date(2026, 2, 1))

        self.assertTrue(result)
        # Finalize is called from check_season_transition
        self.mock_data_manager.finalize_season_rankings.assert_called_with(1)
        self.mock_data_manager.end_season.assert_called_with(1)
        self.mock_data_manager.create_season.assert_called_once()

    def test_finalize_season(self):
        """Test season finalization."""
        season = Season(1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True)
        self.mock_data_manager.get_season_by_id.return_value = season

        self.manager.finalize_season(season.season_id)

        self.mock_data_manager.finalize_season_rankings.assert_called_once_with(1)
        self.mock_data_manager.end_season.assert_called_once_with(1)

    def test_get_season_leaderboard(self):
        """Test season leaderboard retrieval."""
        from src.core.season import SeasonScore
        from src.core.player import Player

        scores = [
            SeasonScore("1", 1, points=1000),
            SeasonScore("2", 1, points=800),
        ]
        self.mock_data_manager.get_season_scores.return_value = scores
        self.mock_data_manager.get_player.side_effect = [
            Player(id="1", name="Alice", score=5000),
            Player(id="2", name="Bob", score=4000),
        ]

        result = self.manager.get_season_leaderboard(1)

        self.assertEqual(len(result), 2)
        # Result is list of tuples (SeasonScore, player_name)
        self.assertEqual(result[0][1], "Alice")  # player_name
        self.assertEqual(result[1][1], "Bob")
        self.mock_data_manager.get_season_scores.assert_called_once_with(1, 10)

    def test_get_all_time_leaderboard(self):
        """Test all-time leaderboard retrieval."""
        from src.core.player import Player

        player1 = Player(
            id="1",
            name="Alice",
            score=5000,
            lifetime_questions=100,
            lifetime_correct=80,
        )
        player2 = Player(
            id="2",
            name="Bob",
            score=4000,
            lifetime_questions=90,
            lifetime_correct=70,
        )
        self.mock_data_manager.get_all_players.return_value = {
            "1": player1,
            "2": player2,
        }

        result = self.manager.get_all_time_leaderboard()

        # Result is list of tuples (player_dict, player_name)
        # Should be sorted by score descending
        self.assertEqual(result[0][0]["score"], 5000)  # First tuple's dict
        self.assertEqual(result[0][1], "Alice")  # First tuple's name
        self.assertEqual(result[1][0]["score"], 4000)
        self.assertEqual(result[1][1], "Bob")


class TestSeasonManagerEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_data_manager = MagicMock(spec=DataManager)
        self.mock_config = MagicMock(spec=ConfigReader)
        self.mock_config.get_season_mode.return_value = "calendar"
        self.mock_config.get_season_auto_create.return_value = True
        self.mock_config.get_season_trophy_positions.return_value = 3
        self.mock_config.is_seasons_enabled.return_value = True

        self.manager = SeasonManager(self.mock_data_manager, self.mock_config)

    def test_get_or_create_with_seasons_disabled(self):
        """Test behavior when seasons feature is disabled."""
        self.mock_config.is_seasons_enabled.return_value = False
        self.manager = SeasonManager(self.mock_data_manager, self.mock_config)

        result = self.manager.get_or_create_current_season()

        self.assertIsNone(result)
        self.mock_data_manager.create_season.assert_not_called()

    def test_finalize_season_not_found(self):
        """Test finalizing non-existent season."""
        self.mock_data_manager.get_season_by_id.return_value = None

        # Should not raise an error
        self.manager.finalize_season(999)

        self.mock_data_manager.finalize_season_rankings.assert_not_called()


if __name__ == "__main__":
    unittest.main()
