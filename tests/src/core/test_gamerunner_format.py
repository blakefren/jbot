import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from data.readers.question import Question
from db.database import Database
from src.cfg.main import ConfigReader
from src.core.data_manager import DataManager
from src.core.game_runner import GameRunner
from src.core.player_manager import PlayerManager


def _make_config(seasons_enabled=False, auto_create=True):
    # ConfigReader is an external boundary (reads .env / sources.toml)
    cfg = MagicMock(spec=ConfigReader)
    values = {"JBOT_EMOJI_STREAK": "🔥", "JBOT_TIMEZONE": "UTC"}
    cfg.get.side_effect = lambda key, default=None: values.get(key, default)
    cfg.is_seasons_enabled.return_value = seasons_enabled
    cfg.get_season_mode.return_value = "calendar"
    cfg.get_season_auto_create.return_value = auto_create
    cfg.get_season_announce_start.return_value = False
    cfg.get_season_announce_end.return_value = False
    cfg.get_season_trophy_positions.return_value = 3
    cfg.get_season_duration_days.return_value = 30
    cfg.get_season_reminder_days.return_value = 3
    return cfg


class _RealStackTestCase(unittest.TestCase):
    seasons_enabled = False
    auto_create = True

    def setUp(self):
        self.db = Database(":memory:")
        self.data_manager = DataManager(self.db)
        self.player_manager = PlayerManager(self.data_manager)
        config = _make_config(self.seasons_enabled, self.auto_create)
        with patch("src.core.game_runner.ConfigReader", return_value=config):
            self.runner = GameRunner(
                MagicMock(), self.data_manager, player_manager=self.player_manager
            )

    def tearDown(self):
        self.db.close()


class TestGameRunnerFormatAnswer(_RealStackTestCase):
    def setUp(self):
        super().setUp()
        self.question = Question("Q", "Main Answer", "C", 100)
        self.runner.daily_question_id = self.data_manager.log_daily_question(
            self.question
        )
        _, self.runner.question_db_id = self.data_manager.get_daily_question_by_id(
            self.runner.daily_question_id
        )

    def test_format_answer_no_alts(self):
        result = self.runner.format_answer(self.question)
        self.assertIn("Main Answer", result)
        self.assertNotIn("Also accepted", result)

    def test_format_answer_with_alts(self):
        for alt in ("Alt1", "Alt2"):
            self.data_manager.add_alternative_answer(
                self.runner.question_db_id, alt, "admin"
            )
        result = self.runner.format_answer(self.question)
        self.assertIn("Main Answer", result)
        self.assertIn("Also accepted", result)
        self.assertIn("Alt1", result)
        self.assertIn("Alt2", result)


class _LeaderboardTestCase(_RealStackTestCase):
    def setUp(self):
        super().setUp()
        # Pin the clock: March 2, 2026 is day 2 of 31 in the calendar season
        today_patch = patch.object(
            self.runner.season_manager, "_today", return_value=date(2026, 3, 2)
        )
        today_patch.start()
        self.addCleanup(today_patch.stop)

    def _seed_player(self, player_id="p1", name="Alice", score=150):
        self.player_manager.get_or_create_player(player_id, name)
        self.player_manager.update_score(player_id, score)
        # The all-time leaderboard only lists players with recent activity
        daily_question_id = self.data_manager.log_daily_question(
            Question("Q", "A", "C", 100)
        )
        self.data_manager.log_player_guess(
            player_id, name, daily_question_id, "A", True
        )


class TestGetActiveLeaderboardSeasonsDisabled(_LeaderboardTestCase):
    def test_seasons_disabled_calls_all_time(self):
        """When seasons are disabled, get_active_leaderboard returns all-time leaderboard."""
        self._seed_player()

        result = self.runner.get_active_leaderboard(guild=None)

        self.assertIn("Alice", result)
        self.assertNotIn("Day ", result)
        self.assertEqual(self.data_manager.get_all_seasons(), [])


class TestGetActiveLeaderboardNoSeason(_LeaderboardTestCase):
    seasons_enabled = True
    auto_create = False

    def test_seasons_enabled_no_active_season_falls_back_to_all_time(self):
        """When seasons are enabled but no season exists, falls back to all-time."""
        self._seed_player()

        result = self.runner.get_active_leaderboard(guild=None)

        self.assertIn("Alice", result)
        self.assertNotIn("Day ", result)
        self.assertEqual(self.data_manager.get_all_seasons(), [])


class TestGetActiveLeaderboardSeasonsEnabled(_LeaderboardTestCase):
    seasons_enabled = True

    def test_seasons_enabled_with_active_season_returns_season_lb(self):
        """When seasons are enabled and a season exists, returns formatted season leaderboard."""
        self._seed_player()
        season = self.runner.season_manager.get_or_create_current_season()
        self.data_manager.update_season_score(
            "p1", season.season_id, points=150, current_streak=3
        )

        result = self.runner.get_active_leaderboard(guild=None)

        self.assertIn("March 2026", result)
        self.assertIn("Alice", result)
        self.assertIn("150", result)

    def test_season_leaderboard_header_contains_day_progress(self):
        """Season leaderboard header shows current day and total days."""
        result = self.runner.get_active_leaderboard()

        self.assertIn("Day 2/31", result)

    def test_season_leaderboard_no_scores_message(self):
        """When the season exists but has no scores, returns appropriate message."""
        result = self.runner.get_active_leaderboard()

        self.assertIn("No scores this season yet", result)
