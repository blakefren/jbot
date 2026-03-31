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

        with patch("src.core.season_manager.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 15)
            result = self.manager.get_or_create_current_season()

        self.assertEqual(result, active_season)
        self.mock_data_manager.create_season.assert_not_called()

    def test_get_or_create_current_season_no_season(self):
        """Test creating new season when none exists and auto-create is on."""
        self.mock_config.get_season_auto_create.return_value = True
        new_season = Season(
            1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True
        )
        # check_season_transition sees None, creates; get_or_create re-fetches the new season
        self.mock_data_manager.get_current_season.side_effect = [None, new_season]
        self.mock_data_manager.get_season_by_id.return_value = new_season

        with patch("src.core.season_manager.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 15)
            result = self.manager.get_or_create_current_season()

        self.assertEqual(result, new_season)
        self.mock_data_manager.create_season.assert_called_once()

    def test_get_or_create_current_season_no_season_auto_create_disabled(self):
        """Test that no season is created when none exists and auto-create is off."""
        self.mock_config.get_season_auto_create.return_value = False
        self.mock_data_manager.get_current_season.return_value = None

        with patch("src.core.season_manager.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 15)
            result = self.manager.get_or_create_current_season()

        self.assertIsNone(result)
        self.mock_data_manager.create_season.assert_not_called()

    def test_get_or_create_current_season_expired(self):
        """Test handling expired season: delegates to check_season_transition."""
        expired_season = Season(
            1, "December 2025", date(2025, 12, 1), date(2025, 12, 31), True
        )
        new_season = Season(
            2, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True
        )
        # check_season_transition sees expired, finalizes; get_or_create re-fetches new season
        self.mock_data_manager.get_current_season.side_effect = [
            expired_season,
            new_season,
        ]
        self.mock_data_manager.get_season_by_id.return_value = new_season
        self.mock_config.get_season_announce_end.return_value = False
        self.mock_config.get_season_announce_start.return_value = False

        with patch("src.core.season_manager.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 15)
            result = self.manager.get_or_create_current_season()

        # Should finalize old season and create new one via check_season_transition
        self.mock_data_manager.finalize_season_rankings.assert_called_once_with(1, 3)
        self.mock_data_manager.end_season.assert_called_once_with(1)
        self.mock_data_manager.create_season.assert_called_once()
        self.assertEqual(result, new_season)

    def test_check_season_transition_same_month(self):
        """Test check_season_transition when still in same month."""
        current_season = Season(
            1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True
        )
        self.mock_data_manager.get_current_season.return_value = current_season

        with patch("src.core.season_manager.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 15)
            transitioned, msgs = self.manager.check_season_transition()

        self.assertFalse(transitioned)
        self.assertEqual(msgs, [])
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

        transitioned, msgs = self.manager.check_season_transition(date(2026, 2, 1))

        self.assertTrue(transitioned)
        # Finalize is called from check_season_transition
        self.mock_data_manager.finalize_season_rankings.assert_called_with(1, 3)
        self.mock_data_manager.end_season.assert_called_with(1)
        self.mock_data_manager.create_season.assert_called_once()

    def test_check_season_transition_no_season_auto_create_disabled(self):
        """check_season_transition returns (False, []) when no season and auto-create is off."""
        self.mock_config.get_season_auto_create.return_value = False
        self.mock_data_manager.get_current_season.return_value = None

        transitioned, msgs = self.manager.check_season_transition(date(2026, 1, 15))

        self.assertFalse(transitioned)
        self.assertEqual(msgs, [])
        self.mock_data_manager.create_season.assert_not_called()

    def test_finalize_season(self):
        """Test season finalization."""
        season = Season(1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True)
        self.mock_data_manager.get_season_by_id.return_value = season
        self.mock_config.get_season_trophy_positions.return_value = 3

        self.manager.finalize_season(season.season_id)

        self.mock_data_manager.finalize_season_rankings.assert_called_once_with(1, 3)
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
        self.mock_data_manager.get_season_scores.assert_called_once_with(1, 25)

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


class TestSeasonManagerAnnouncements(unittest.TestCase):
    """Tests for announcement builder methods."""

    def setUp(self):
        self.mock_data_manager = MagicMock(spec=DataManager)
        self.mock_config = MagicMock(spec=ConfigReader)
        self.mock_config.is_seasons_enabled.return_value = True
        self.mock_config.get_season_mode.return_value = "calendar"
        self.mock_config.get_season_trophy_positions.return_value = 3
        self.manager = SeasonManager(self.mock_data_manager, self.mock_config)

    # ── build_season_end_announcement ─────────────────────────────────────────

    def test_build_season_end_announcement_with_trophy_winners(self):
        """Trophy winners appear with their emoji and points."""
        season = Season(1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True)
        gold = SeasonScore("1", 1, points=1000, trophy="gold")
        silver = SeasonScore("2", 1, points=800, trophy="silver")
        no_trophy = SeasonScore("3", 1, points=500, trophy=None)
        leaderboard = [(gold, "Alice"), (silver, "Bob"), (no_trophy, "Carol")]

        msg = self.manager.build_season_end_announcement(season, leaderboard)

        self.assertIn("January 2026", msg)
        self.assertIn("🥇", msg)
        self.assertIn("Alice", msg)
        self.assertIn("🥈", msg)
        self.assertIn("Bob", msg)
        # Carol has no trophy, should not appear in winners list
        self.assertNotIn("Carol", msg)

    def test_build_season_end_announcement_no_participants(self):
        """Empty leaderboard shows 'No players participated'."""
        season = Season(1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True)
        msg = self.manager.build_season_end_announcement(season, [])
        self.assertIn("No players participated", msg)

    def test_build_season_end_announcement_no_trophies(self):
        """Leaderboard with no trophy winners shows 'No players participated'."""
        season = Season(1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True)
        score = SeasonScore("1", 1, points=500, trophy=None)
        msg = self.manager.build_season_end_announcement(season, [(score, "Alice")])
        self.assertIn("No players participated", msg)

    def test_build_season_end_announcement_shows_total_count(self):
        """Total participant count appears when leaderboard is non-empty."""
        season = Season(1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True)
        gold = SeasonScore("1", 1, points=1000, trophy="gold")
        msg = self.manager.build_season_end_announcement(season, [(gold, "Alice")])
        self.assertIn("1 player(s) competed", msg)

    # ── build_new_season_announcement ─────────────────────────────────────────

    def test_build_new_season_announcement_no_challenge(self):
        """New-season announcement includes season name and reset notice."""
        season = Season(2, "February 2026", date(2026, 2, 1), date(2026, 2, 28), True)
        msg = self.manager.build_new_season_announcement(season, challenge=None)
        self.assertIn("February 2026", msg)
        self.assertIn("Points reset", msg)
        self.assertNotIn("Challenge", msg)

    def test_build_new_season_announcement_with_challenge(self):
        """Challenge name and description appear when challenge is provided."""
        season = Season(2, "February 2026", date(2026, 2, 1), date(2026, 2, 28), True)
        mock_challenge = MagicMock()
        mock_challenge.badge_emoji = "🔥"
        mock_challenge.challenge_name = "Speed Demon"
        mock_challenge.description = "Answer first 10 times."

        msg = self.manager.build_new_season_announcement(
            season, challenge=mock_challenge
        )

        self.assertIn("Speed Demon", msg)
        self.assertIn("🔥", msg)
        self.assertIn("Answer first 10 times.", msg)

    # ── build_season_reminder ─────────────────────────────────────────────────

    def test_build_season_reminder_singular_day(self):
        """Uses 'day' (not 'days') when days_remaining == 1."""
        season = Season(1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True)
        msg = self.manager.build_season_reminder(season, [], days_remaining=1)
        self.assertIn("1 day left", msg)
        self.assertNotIn("1 days", msg)

    def test_build_season_reminder_plural_days(self):
        """Uses 'days' when days_remaining > 1."""
        season = Season(1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True)
        msg = self.manager.build_season_reminder(season, [], days_remaining=5)
        self.assertIn("5 days left", msg)

    def test_build_season_reminder_shows_top_5(self):
        """Top 5 standings appear, extras are omitted."""
        season = Season(1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True)
        leaderboard = [
            (SeasonScore(str(i), 1, points=1000 - i * 100), f"Player{i}")
            for i in range(1, 8)  # 7 players
        ]
        msg = self.manager.build_season_reminder(season, leaderboard, days_remaining=3)
        self.assertIn("Player1", msg)
        self.assertIn("Player5", msg)
        self.assertNotIn("Player6", msg)
        self.assertNotIn("Player7", msg)

    def test_build_season_reminder_empty_leaderboard(self):
        """Empty leaderboard omits standings section but still shows countdown."""
        season = Season(1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True)
        msg = self.manager.build_season_reminder(season, [], days_remaining=3)
        self.assertIn("3 days left", msg)
        self.assertNotIn("standings", msg)

    # ── get_reminder_announcement ─────────────────────────────────────────────

    def test_get_reminder_announcement_not_reminder_day(self):
        """Returns None when today is not the scheduled reminder day."""
        season = Season(1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True)
        self.mock_data_manager.get_current_season.return_value = season
        self.mock_config.get_season_announce_end.return_value = True
        self.mock_config.get_season_reminder_days.return_value = 5

        with patch("src.core.season_manager.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 15)  # 16 days left, not 5
            result = self.manager.get_reminder_announcement()

        self.assertIsNone(result)

    def test_get_reminder_announcement_on_reminder_day(self):
        """Returns a formatted reminder string on the scheduled reminder day."""
        season = Season(1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True)
        self.mock_data_manager.get_current_season.return_value = season
        self.mock_data_manager.get_season_scores.return_value = []
        self.mock_config.get_season_announce_end.return_value = True
        self.mock_config.get_season_reminder_days.return_value = 5

        with patch("src.core.season_manager.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 26)  # exactly 5 days left
            result = self.manager.get_reminder_announcement()

        self.assertIsNotNone(result)
        self.assertIn("5 days left", result)

    def test_get_reminder_announcement_disabled(self):
        """Returns None when seasons are disabled."""
        self.mock_config.is_seasons_enabled.return_value = False
        manager = SeasonManager(self.mock_data_manager, self.mock_config)
        result = manager.get_reminder_announcement()
        self.assertIsNone(result)

    def test_get_reminder_announcement_no_current_season(self):
        """Returns None when there is no active season."""
        self.mock_data_manager.get_current_season.return_value = None
        result = self.manager.get_reminder_announcement()
        self.assertIsNone(result)

    # ── check_season_transition return shape ──────────────────────────────────

    def test_check_season_transition_returns_tuple_when_disabled(self):
        """Returns (False, []) tuple when seasons are disabled."""
        self.mock_config.is_seasons_enabled.return_value = False
        manager = SeasonManager(self.mock_data_manager, self.mock_config)
        transitioned, msgs = manager.check_season_transition()
        self.assertFalse(transitioned)
        self.assertEqual(msgs, [])

    def test_check_season_transition_includes_end_message_when_configured(self):
        """Transition builds end announcement when JBOT_SEASON_ANNOUNCE_END=True."""
        old_season = Season(
            1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True
        )
        new_season = Season(
            2, "February 2026", date(2026, 2, 1), date(2026, 2, 28), True
        )
        self.mock_data_manager.get_current_season.return_value = old_season
        self.mock_data_manager.get_season_by_id.return_value = new_season
        self.mock_data_manager.get_season_scores.return_value = []
        self.mock_config.get_season_announce_end.return_value = True
        self.mock_config.get_season_announce_start.return_value = False
        self.mock_config.get_season_mode.return_value = "calendar"
        self.mock_config.get_season_auto_create.return_value = True

        transitioned, msgs = self.manager.check_season_transition(date(2026, 2, 1))

        self.assertTrue(transitioned)
        self.assertEqual(len(msgs), 1)
        self.assertIn("January 2026", msgs[0])

    def test_check_season_transition_includes_start_message_when_configured(self):
        """Transition builds new-season announcement when JBOT_SEASON_ANNOUNCE_START=True."""
        old_season = Season(
            1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True
        )
        new_season = Season(
            2, "February 2026", date(2026, 2, 1), date(2026, 2, 28), True
        )
        self.mock_data_manager.get_current_season.return_value = old_season
        self.mock_data_manager.get_season_by_id.return_value = new_season
        self.mock_data_manager.get_season_challenge.return_value = None
        self.mock_config.get_season_announce_end.return_value = False
        self.mock_config.get_season_announce_start.return_value = True
        self.mock_config.get_season_mode.return_value = "calendar"
        self.mock_config.get_season_auto_create.return_value = True

        transitioned, msgs = self.manager.check_season_transition(date(2026, 2, 1))

        self.assertTrue(transitioned)
        self.assertEqual(len(msgs), 1)
        self.assertIn("February 2026", msgs[0])

    def test_check_season_transition_no_msgs_when_both_disabled(self):
        """Transition returns empty msgs list when both announce flags are False."""
        old_season = Season(
            1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True
        )
        new_season = Season(
            2, "February 2026", date(2026, 2, 1), date(2026, 2, 28), True
        )
        self.mock_data_manager.get_current_season.return_value = old_season
        self.mock_data_manager.get_season_by_id.return_value = new_season
        self.mock_config.get_season_announce_end.return_value = False
        self.mock_config.get_season_announce_start.return_value = False
        self.mock_config.get_season_mode.return_value = "calendar"
        self.mock_config.get_season_auto_create.return_value = True

        transitioned, msgs = self.manager.check_season_transition(date(2026, 2, 1))

        self.assertTrue(transitioned)
        self.assertEqual(msgs, [])


if __name__ == "__main__":
    unittest.main()
