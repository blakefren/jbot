"""
Tests for SeasonManager backed by a real in-memory database.

Only the config (ConfigReader) and the clock (``_today``) are faked.
"""

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from db.database import Database
from src.cfg.main import ConfigReader
from src.core.data_manager import DataManager
from src.core.season import Season, SeasonScore
from src.core.season_manager import SeasonManager


def _make_config(seasons_enabled=True) -> MagicMock:
    # ConfigReader is an external boundary (reads .env / sources.toml)
    cfg = MagicMock(spec=ConfigReader)
    cfg.get.return_value = "UTC"
    cfg.is_seasons_enabled.return_value = seasons_enabled
    cfg.get_season_mode.return_value = "calendar"
    cfg.get_season_duration_days.return_value = 30
    cfg.get_season_auto_create.return_value = True
    cfg.get_season_trophy_positions.return_value = 3
    cfg.get_season_announce_end.return_value = False
    cfg.get_season_announce_start.return_value = False
    cfg.get_season_reminder_days.return_value = 3
    return cfg


class _SeasonTestCase(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.data_manager = DataManager(self.db)
        self.config = _make_config()
        self.manager = SeasonManager(self.data_manager, self.config)

    def tearDown(self):
        self.db.close()

    def _create_january(self) -> int:
        return self.data_manager.create_season(
            "January 2026", "2026-01-01", "2026-01-31"
        )

    def _seed_scores(self, season_id, points_by_player):
        for player_id, points in points_by_player.items():
            self.data_manager.create_player(player_id, player_id.title())
            self.data_manager.update_season_score(player_id, season_id, points=points)


class TestSeasonManager(_SeasonTestCase):
    """Test SeasonManager functionality."""

    def test_get_or_create_current_season_active_exists(self):
        """Test getting current season when one exists."""
        season_id = self._create_january()

        with patch.object(self.manager, "_today", return_value=date(2026, 1, 15)):
            result = self.manager.get_or_create_current_season()

        self.assertEqual(result.season_id, season_id)
        self.assertEqual(len(self.data_manager.get_all_seasons()), 1)

    def test_get_or_create_current_season_no_season(self):
        """Test creating new season when none exists and auto-create is on."""
        with patch.object(self.manager, "_today", return_value=date(2026, 1, 15)):
            result = self.manager.get_or_create_current_season()

        self.assertEqual(result.season_name, "January 2026")
        self.assertTrue(result.is_active)
        self.assertEqual(len(self.data_manager.get_all_seasons()), 1)

    def test_get_or_create_current_season_no_season_auto_create_disabled(self):
        """Test that no season is created when none exists and auto-create is off."""
        self.config.get_season_auto_create.return_value = False

        with patch.object(self.manager, "_today", return_value=date(2026, 1, 15)):
            result = self.manager.get_or_create_current_season()

        self.assertIsNone(result)
        self.assertEqual(self.data_manager.get_all_seasons(), [])

    def test_get_or_create_current_season_expired(self):
        """Test handling expired season: delegates to check_season_transition."""
        december_id = self.data_manager.create_season(
            "December 2025", "2025-12-01", "2025-12-31"
        )
        self._seed_scores(december_id, {"alice": 300, "bob": 200, "carol": 100})

        with patch.object(self.manager, "_today", return_value=date(2026, 1, 15)):
            result = self.manager.get_or_create_current_season()

        # Old season is finalized (trophies awarded, marked inactive)
        december = self.data_manager.get_season_by_id(december_id)
        self.assertFalse(december.is_active)
        trophies = {
            pid: self.data_manager.get_player_season_score(pid, december_id).trophy
            for pid in ("alice", "bob", "carol")
        }
        self.assertEqual(
            trophies, {"alice": "gold", "bob": "silver", "carol": "bronze"}
        )
        # And a new season is active
        self.assertEqual(result.season_name, "January 2026")
        self.assertNotEqual(result.season_id, december_id)
        self.assertEqual(
            self.data_manager.get_current_season().season_id, result.season_id
        )

    def test_check_season_transition_same_month(self):
        """Test check_season_transition when still in same month."""
        season_id = self._create_january()

        with patch.object(self.manager, "_today", return_value=date(2026, 1, 15)):
            transitioned, msgs = self.manager.check_season_transition()

        self.assertFalse(transitioned)
        self.assertEqual(msgs, [])
        self.assertTrue(self.data_manager.get_season_by_id(season_id).is_active)
        self.assertEqual(len(self.data_manager.get_all_seasons()), 1)

    def test_check_season_transition_new_month(self):
        """Test check_season_transition at month boundary."""
        january_id = self._create_january()
        self._seed_scores(january_id, {"alice": 300, "bob": 200})

        transitioned, msgs = self.manager.check_season_transition(date(2026, 2, 1))

        self.assertTrue(transitioned)
        january = self.data_manager.get_season_by_id(january_id)
        self.assertFalse(january.is_active)
        self.assertEqual(
            self.data_manager.get_player_season_score("alice", january_id).trophy,
            "gold",
        )
        current = self.data_manager.get_current_season()
        self.assertEqual(current.season_name, "February 2026")
        self.assertEqual(len(self.data_manager.get_all_seasons()), 2)

    def test_check_season_transition_no_season_auto_create_disabled(self):
        """check_season_transition returns (False, []) when no season and auto-create is off."""
        self.config.get_season_auto_create.return_value = False

        transitioned, msgs = self.manager.check_season_transition(date(2026, 1, 15))

        self.assertFalse(transitioned)
        self.assertEqual(msgs, [])
        self.assertEqual(self.data_manager.get_all_seasons(), [])

    def test_finalize_season(self):
        """Test season finalization."""
        season_id = self._create_january()
        self._seed_scores(
            season_id, {"alice": 400, "bob": 300, "carol": 200, "dave": 100}
        )

        self.manager.finalize_season(season_id)

        self.assertFalse(self.data_manager.get_season_by_id(season_id).is_active)
        trophies = {
            pid: self.data_manager.get_player_season_score(pid, season_id).trophy
            for pid in ("alice", "bob", "carol", "dave")
        }
        self.assertEqual(
            trophies,
            {"alice": "gold", "bob": "silver", "carol": "bronze", "dave": None},
        )

    def test_get_season_leaderboard(self):
        """Test season leaderboard retrieval."""
        season_id = self._create_january()
        self._seed_scores(season_id, {"bob": 800, "alice": 1000})

        result = self.manager.get_season_leaderboard(season_id)

        self.assertEqual(
            [(score.points, name) for score, name in result],
            [(1000, "Alice"), (800, "Bob")],
        )

    def test_get_season_leaderboard_defaults_to_top_25(self):
        """Leaderboard is limited to 25 entries by default."""
        season_id = self._create_january()
        self._seed_scores(season_id, {f"p{i:02d}": i for i in range(30)})

        result = self.manager.get_season_leaderboard(season_id)

        self.assertEqual(len(result), 25)
        self.assertEqual(result[0][0].points, 29)

    def test_get_all_time_leaderboard(self):
        """Test all-time leaderboard retrieval."""
        for player_id, name, score in (("1", "Bob", 4000), ("2", "Alice", 5000)):
            self.data_manager.create_player(player_id, name)
            self.data_manager.update_lifetime_stats(
                player_id, score=score, lifetime_questions=100, lifetime_correct=80
            )

        result = self.manager.get_all_time_leaderboard()

        # Result is list of tuples (player_dict, player_name) sorted by score
        self.assertEqual(result[0][0]["score"], 5000)
        self.assertEqual(result[0][1], "Alice")
        self.assertEqual(result[0][0]["lifetime_questions"], 100)
        self.assertEqual(result[1][0]["score"], 4000)
        self.assertEqual(result[1][1], "Bob")


class TestSeasonManagerEdgeCases(_SeasonTestCase):
    """Test edge cases and error conditions."""

    def test_get_or_create_with_seasons_disabled(self):
        """Test behavior when seasons feature is disabled."""
        self.config.is_seasons_enabled.return_value = False
        manager = SeasonManager(self.data_manager, self.config)

        result = manager.get_or_create_current_season()

        self.assertIsNone(result)
        self.assertEqual(self.data_manager.get_all_seasons(), [])

    def test_finalize_season_not_found(self):
        """Test finalizing non-existent season."""
        # Should not raise an error
        self.manager.finalize_season(999)

        self.assertEqual(self.data_manager.get_all_seasons(), [])


class TestSeasonManagerAnnouncements(_SeasonTestCase):
    """Tests for announcement builder methods."""

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
        """Leaderboard with players but no trophies shows competed count, not 'no participants'."""
        season = Season(1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True)
        score = SeasonScore("1", 1, points=500, trophy=None)
        msg = self.manager.build_season_end_announcement(season, [(score, "Alice")])
        self.assertIn("1 player(s) competed", msg)
        self.assertNotIn("No players participated", msg)

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
        season_id = self.data_manager.create_season(
            "February 2026", "2026-02-01", "2026-02-28"
        )
        self.data_manager.create_season_challenge(
            season_id, "Speed Demon", "Answer first 10 times.", "🔥", {"count": 10}
        )
        season = self.data_manager.get_season_by_id(season_id)
        challenge = self.data_manager.get_season_challenge(season_id)

        msg = self.manager.build_new_season_announcement(season, challenge=challenge)

        self.assertIn("Speed Demon", msg)
        self.assertIn("🔥", msg)
        self.assertIn("Answer first 10 times.", msg)

    # ── build_season_reminder ─────────────────────────────────────────────────

    def test_build_season_reminder_singular_day(self):
        """Uses 'day' (not 'days') when days_remaining == 1."""
        season = Season(1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True)
        msg = self.manager.build_season_reminder(season, days_remaining=1)
        self.assertIn("1 day left", msg)
        self.assertNotIn("1 days", msg)

    def test_build_season_reminder_plural_days(self):
        """Uses 'days' when days_remaining > 1."""
        season = Season(1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True)
        msg = self.manager.build_season_reminder(season, days_remaining=5)
        self.assertIn("5 days left", msg)

    def test_build_season_reminder_shows_season_name(self):
        """Reminder includes the season name and day count."""
        season = Season(1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True)
        msg = self.manager.build_season_reminder(season, days_remaining=3)
        self.assertIn("January 2026", msg)
        self.assertIn("3 days left", msg)

    def test_build_season_reminder_no_leaderboard_section(self):
        """Reminder no longer embeds standings (leaderboard is in the daily message)."""
        season = Season(1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True)
        msg = self.manager.build_season_reminder(season, days_remaining=3)
        self.assertIn("3 days left", msg)
        self.assertNotIn("standings", msg)

    # ── get_reminder_announcement ─────────────────────────────────────────────

    def test_get_reminder_announcement_not_reminder_day(self):
        """Returns None when today is not the scheduled reminder day."""
        self._create_january()
        self.config.get_season_announce_end.return_value = True
        self.config.get_season_reminder_days.return_value = 5

        with patch.object(self.manager, "_today", return_value=date(2026, 1, 15)):
            result = self.manager.get_reminder_announcement()

        self.assertIsNone(result)

    def test_get_reminder_announcement_on_reminder_day(self):
        """Returns a formatted reminder string on the scheduled reminder day."""
        self._create_january()
        self.config.get_season_announce_end.return_value = True
        self.config.get_season_reminder_days.return_value = 5

        with patch.object(self.manager, "_today", return_value=date(2026, 1, 26)):
            result = self.manager.get_reminder_announcement()

        self.assertIsNotNone(result)
        self.assertIn("5 days left", result)

    def test_get_reminder_announcement_disabled(self):
        """Returns None when seasons are disabled."""
        self.config.is_seasons_enabled.return_value = False
        manager = SeasonManager(self.data_manager, self.config)
        result = manager.get_reminder_announcement()
        self.assertIsNone(result)

    def test_get_reminder_announcement_no_current_season(self):
        """Returns None when there is no active season."""
        result = self.manager.get_reminder_announcement()
        self.assertIsNone(result)

    # ── get_season_end_announcement ───────────────────────────────────────────

    def test_get_season_end_announcement_on_last_day(self):
        """Returns end announcement when today is the last day of the season."""
        season_id = self._create_january()
        self.config.get_season_announce_end.return_value = True

        with patch.object(self.manager, "_today", return_value=date(2026, 1, 31)):
            result = self.manager.get_season_end_announcement()

        self.assertIsNotNone(result)
        self.assertIn("January 2026", result)
        self.assertFalse(self.data_manager.get_season_by_id(season_id).is_active)

    def test_get_season_end_announcement_calls_finalize_before_leaderboard(self):
        """Rankings are finalized before the leaderboard is built,
        so trophies are present in the announcement."""
        season_id = self._create_january()
        self._seed_scores(season_id, {"alice": 300, "bob": 200})
        self.config.get_season_announce_end.return_value = True

        with patch.object(self.manager, "_today", return_value=date(2026, 1, 31)):
            result = self.manager.get_season_end_announcement()

        self.assertIn("🥇 **Alice** — 300 pts", result)
        self.assertIn("🥈 **Bob** — 200 pts", result)

    def test_get_season_end_announcement_not_last_day(self):
        """Returns None when today is not the last day of the season."""
        season_id = self._create_january()
        self.config.get_season_announce_end.return_value = True

        with patch.object(self.manager, "_today", return_value=date(2026, 1, 30)):
            result = self.manager.get_season_end_announcement()

        self.assertIsNone(result)
        self.assertTrue(self.data_manager.get_season_by_id(season_id).is_active)

    def test_get_season_end_announcement_disabled(self):
        """Returns None when announce_end is False."""
        season_id = self._create_january()
        self.config.get_season_announce_end.return_value = False

        with patch.object(self.manager, "_today", return_value=date(2026, 1, 31)):
            result = self.manager.get_season_end_announcement()

        self.assertIsNone(result)
        self.assertTrue(self.data_manager.get_season_by_id(season_id).is_active)

    # ── check_season_transition return shape ──────────────────────────────────

    def test_check_season_transition_returns_tuple_when_disabled(self):
        """Returns (False, []) tuple when seasons are disabled."""
        self.config.is_seasons_enabled.return_value = False
        manager = SeasonManager(self.data_manager, self.config)
        transitioned, msgs = manager.check_season_transition()
        self.assertFalse(transitioned)
        self.assertEqual(msgs, [])

    def test_check_season_transition_no_end_message_in_transition(self):
        """Transition no longer includes end announcement (it fires via get_season_end_announcement on the last day instead)."""
        self._create_january()
        self.config.get_season_announce_end.return_value = True

        transitioned, msgs = self.manager.check_season_transition(date(2026, 2, 1))

        self.assertTrue(transitioned)
        # End announcement is no longer part of the transition msgs
        self.assertEqual(msgs, [])

    def test_check_season_transition_includes_start_message_when_configured(self):
        """Transition builds new-season announcement when JBOT_SEASON_ANNOUNCE_START=True."""
        self._create_january()
        self.config.get_season_announce_start.return_value = True

        transitioned, msgs = self.manager.check_season_transition(date(2026, 2, 1))

        self.assertTrue(transitioned)
        self.assertEqual(len(msgs), 1)
        self.assertIn("February 2026", msgs[0])

    def test_check_season_transition_no_msgs_when_both_disabled(self):
        """Transition returns empty msgs list when both announce flags are False."""
        self._create_january()

        transitioned, msgs = self.manager.check_season_transition(date(2026, 2, 1))

        self.assertTrue(transitioned)
        self.assertEqual(msgs, [])


if __name__ == "__main__":
    unittest.main()
