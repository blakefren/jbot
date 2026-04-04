"""
Integration tests for SeasonManager backed by a real in-memory database.

Unlike the existing mock-based tests in test_season_manager.py which verify
SeasonManager's logic in isolation, these tests run the full stack
(SeasonManager → DataManager → SQLite) so that SQL errors and schema
mismatches are caught automatically.
"""

import unittest
from datetime import date
from unittest.mock import MagicMock

from db.database import Database
from src.core.data_manager import DataManager
from src.core.season_manager import SeasonManager
from src.core.season import Season
from src.cfg.main import ConfigReader


def _make_config(
    enabled: bool = True,
    mode: str = "calendar",
    auto_create: bool = True,
    announce_end: bool = False,
    announce_start: bool = False,
    trophy_positions: int = 3,
    duration_days: int = 30,
    reminder_days: int = 3,
) -> MagicMock:
    cfg = MagicMock(spec=ConfigReader)
    cfg.get.side_effect = lambda k, d=None: {"JBOT_TIMEZONE": "UTC"}.get(k, d)
    cfg.is_seasons_enabled.return_value = enabled
    cfg.get_season_mode.return_value = mode
    cfg.get_season_auto_create.return_value = auto_create
    cfg.get_season_announce_end.return_value = announce_end
    cfg.get_season_announce_start.return_value = announce_start
    cfg.get_season_trophy_positions.return_value = trophy_positions
    cfg.get_season_duration_days.return_value = duration_days
    cfg.get_season_reminder_days.return_value = reminder_days
    return cfg


def _make_stack(
    **cfg_kwargs,
) -> tuple[Database, DataManager, SeasonManager, MagicMock]:
    db = Database(":memory:")
    dm = DataManager(db)
    dm.initialize_database()
    cfg = _make_config(**cfg_kwargs)
    sm = SeasonManager(dm, cfg)
    return db, dm, sm, cfg


def _create_player(dm: DataManager, player_id: str, name: str = "Player") -> None:
    dm.create_player(player_id, name)


class TestSeasonManagerIntegrationBasic(unittest.TestCase):
    """Stack-level tests for core SeasonManager lifecycle methods."""

    def setUp(self):
        self.db, self.dm, self.sm, self.cfg = _make_stack()

    def tearDown(self):
        self.db.close()

    # --- get_or_create_current_season ---

    def test_get_or_create_creates_season_when_none_exists(self):
        with unittest.mock.patch.object(
            self.sm, "_today", return_value=date(2026, 1, 15)
        ):
            season = self.sm.get_or_create_current_season()
        self.assertIsNotNone(season)
        self.assertIsInstance(season, Season)
        self.assertTrue(season.is_active)

    def test_get_or_create_returns_existing_season(self):
        with unittest.mock.patch.object(
            self.sm, "_today", return_value=date(2026, 1, 15)
        ):
            season1 = self.sm.get_or_create_current_season()
            season2 = self.sm.get_or_create_current_season()
        # Only one season should exist
        all_seasons = self.dm.get_all_seasons()
        self.assertEqual(len(all_seasons), 1)
        self.assertEqual(season1.season_id, season2.season_id)

    def test_get_or_create_disabled_returns_none(self):
        _, _, sm, _ = _make_stack(enabled=False)
        result = sm.get_or_create_current_season()
        self.assertIsNone(result)

    def test_get_or_create_auto_create_off_returns_none_when_no_season(self):
        db, _, sm, _ = _make_stack(auto_create=False)
        try:
            with unittest.mock.patch.object(
                sm, "_today", return_value=date(2026, 1, 15)
            ):
                result = sm.get_or_create_current_season()
            self.assertIsNone(result)
        finally:
            db.close()

    # --- check_season_transition ---

    def test_no_transition_mid_season(self):
        # Create an active season spanning all of January
        self.dm.create_season("January 2026", "2026-01-01", "2026-01-31")
        transitioned, msgs = self.sm.check_season_transition(date(2026, 1, 15))
        self.assertFalse(transitioned)
        self.assertEqual(msgs, [])

    def test_transition_when_season_expired(self):
        self.dm.create_season("January 2026", "2026-01-01", "2026-01-31")
        # On Feb 1, the January season has ended
        transitioned, msgs = self.sm.check_season_transition(date(2026, 2, 1))
        self.assertTrue(transitioned)
        # January season should now be inactive
        all_seasons = self.dm.get_all_seasons()
        jan = next(s for s in all_seasons if s.season_name == "January 2026")
        self.assertFalse(jan.is_active)
        # A new season should have been created
        active = self.dm.get_current_season()
        self.assertIsNotNone(active)
        self.assertNotEqual(active.season_id, jan.season_id)

    def test_transition_no_season_auto_create_on(self):
        transitioned, msgs = self.sm.check_season_transition(date(2026, 1, 15))
        self.assertTrue(transitioned)
        self.assertIsNotNone(self.dm.get_current_season())

    def test_transition_no_season_auto_create_off(self):
        db, dm, sm, _ = _make_stack(auto_create=False)
        try:
            transitioned, msgs = sm.check_season_transition(date(2026, 1, 15))
            self.assertFalse(transitioned)
            self.assertIsNone(dm.get_current_season())
        finally:
            db.close()


class TestSeasonManagerIntegrationCalendarMode(unittest.TestCase):
    """Tests for calendar-mode season creation."""

    def setUp(self):
        self.db, self.dm, self.sm, _ = _make_stack(mode="calendar")

    def tearDown(self):
        self.db.close()

    def test_calendar_season_spans_correct_month(self):
        with unittest.mock.patch.object(
            self.sm, "_today", return_value=date(2026, 3, 10)
        ):
            self.sm.check_season_transition(date(2026, 3, 10))
        season = self.dm.get_current_season()
        self.assertIsNotNone(season)
        self.assertEqual(season.start_date, date(2026, 3, 1))
        self.assertEqual(season.end_date, date(2026, 3, 31))
        self.assertEqual(season.season_name, "March 2026")

    def test_calendar_season_february(self):
        self.sm.check_season_transition(date(2026, 2, 5))
        season = self.dm.get_current_season()
        self.assertEqual(season.start_date, date(2026, 2, 1))
        self.assertEqual(season.end_date, date(2026, 2, 28))


class TestSeasonManagerIntegrationRollingMode(unittest.TestCase):
    """Tests for rolling-mode season creation."""

    def setUp(self):
        self.db, self.dm, self.sm, _ = _make_stack(mode="rolling", duration_days=14)

    def tearDown(self):
        self.db.close()

    def test_rolling_season_correct_duration(self):
        self.sm.check_season_transition(date(2026, 1, 5))
        season = self.dm.get_current_season()
        self.assertIsNotNone(season)
        total_days = (season.end_date - season.start_date).days + 1
        self.assertEqual(total_days, 14)

    def test_rolling_season_starts_on_given_date(self):
        self.sm.check_season_transition(date(2026, 6, 15))
        season = self.dm.get_current_season()
        self.assertEqual(season.start_date, date(2026, 6, 15))


class TestSeasonManagerIntegrationFinalize(unittest.TestCase):
    """Tests for finalize_season over a real database."""

    def setUp(self):
        self.db, self.dm, self.sm, _ = _make_stack(trophy_positions=3)
        _create_player(self.dm, "p1", "Alice")
        _create_player(self.dm, "p2", "Bob")
        _create_player(self.dm, "p3", "Carol")
        self.season_id = self.dm.create_season("Jan 2026", "2026-01-01", "2026-01-31")

    def tearDown(self):
        self.db.close()

    def test_finalize_season_marks_inactive(self):
        self.sm.finalize_season(self.season_id)
        season = self.dm.get_season_by_id(self.season_id)
        self.assertFalse(season.is_active)

    def test_finalize_season_awards_trophies(self):
        self.dm.update_season_score("p1", self.season_id, points=300)
        self.dm.update_season_score("p2", self.season_id, points=200)
        self.dm.update_season_score("p3", self.season_id, points=100)

        self.sm.finalize_season(self.season_id)

        self.assertEqual(
            self.dm.get_player_season_score("p1", self.season_id).trophy, "gold"
        )
        self.assertEqual(
            self.dm.get_player_season_score("p2", self.season_id).trophy, "silver"
        )
        self.assertEqual(
            self.dm.get_player_season_score("p3", self.season_id).trophy, "bronze"
        )

    def test_finalize_season_missing_id_does_not_raise(self):
        self.sm.finalize_season(9999)


class TestSeasonManagerIntegrationLeaderboard(unittest.TestCase):
    """Tests for get_season_leaderboard over real data."""

    def setUp(self):
        self.db, self.dm, self.sm, _ = _make_stack()
        _create_player(self.dm, "p1", "Alice")
        _create_player(self.dm, "p2", "Bob")
        self.season_id = self.dm.create_season("Jan 2026", "2026-01-01", "2026-01-31")

    def tearDown(self):
        self.db.close()

    def test_leaderboard_returns_players_sorted_by_points(self):
        self.dm.update_season_score("p1", self.season_id, points=100)
        self.dm.update_season_score("p2", self.season_id, points=500)

        leaderboard = self.sm.get_season_leaderboard(self.season_id)

        self.assertEqual(len(leaderboard), 2)
        # Tuples are (SeasonScore, player_name)
        self.assertEqual(leaderboard[0][1], "Bob")
        self.assertEqual(leaderboard[0][0].points, 500)
        self.assertEqual(leaderboard[1][1], "Alice")

    def test_leaderboard_empty_season(self):
        leaderboard = self.sm.get_season_leaderboard(self.season_id)
        self.assertEqual(leaderboard, [])

    def test_leaderboard_uses_current_season_when_no_id_given(self):
        self.dm.update_season_score("p1", self.season_id, points=300)
        # Patch _today so the Jan 2026 season is still active and no transition fires
        with unittest.mock.patch.object(
            self.sm, "_today", return_value=date(2026, 1, 15)
        ):
            leaderboard = self.sm.get_season_leaderboard()
        self.assertEqual(len(leaderboard), 1)

    def test_leaderboard_unknown_player_shows_fallback_name(self):
        # Insert a score for a player not in the players table
        self.dm.update_season_score("ghost", self.season_id, points=50)
        leaderboard = self.sm.get_season_leaderboard(self.season_id)
        names = [name for _, name in leaderboard]
        self.assertTrue(any("ghost" in name for name in names))


class TestSeasonManagerIntegrationPlayerInit(unittest.TestCase):
    """Tests for initialize_player_for_season."""

    def setUp(self):
        self.db, self.dm, self.sm, _ = _make_stack()
        _create_player(self.dm, "p1", "Alice")
        self.season_id = self.dm.create_season("Jan 2026", "2026-01-01", "2026-01-31")

    def tearDown(self):
        self.db.close()

    def test_initialize_player_creates_season_score_row(self):
        self.sm.initialize_player_for_season("p1", self.season_id)
        score = self.dm.get_player_season_score("p1", self.season_id)
        self.assertIsNotNone(score)
        self.assertEqual(score.points, 0)

    def test_initialize_player_idempotent(self):
        self.sm.initialize_player_for_season("p1", self.season_id)
        self.sm.initialize_player_for_season("p1", self.season_id)
        score = self.dm.get_player_season_score("p1", self.season_id)
        self.assertIsNotNone(score)


class TestSeasonManagerIntegrationAnnouncements(unittest.TestCase):
    """Tests for announcement-building methods (no Discord, just string output)."""

    def setUp(self):
        self.db, self.dm, self.sm, _ = _make_stack()
        _create_player(self.dm, "p1", "Alice")
        _create_player(self.dm, "p2", "Bob")
        self.season_id = self.dm.create_season("Jan 2026", "2026-01-01", "2026-01-31")

    def tearDown(self):
        self.db.close()

    def test_build_season_end_announcement_with_trophies(self):
        self.dm.update_season_score("p1", self.season_id, points=400)
        self.dm.update_season_score("p2", self.season_id, points=200)
        self.dm.finalize_season_rankings(self.season_id)
        season = self.dm.get_season_by_id(self.season_id)
        leaderboard = self.sm.get_season_leaderboard(self.season_id)

        msg = self.sm.build_season_end_announcement(season, leaderboard)

        self.assertIn("Jan 2026", msg)
        self.assertIn("Alice", msg)
        self.assertIn("🥇", msg)

    def test_build_season_end_announcement_no_participants(self):
        season = self.dm.get_season_by_id(self.season_id)
        msg = self.sm.build_season_end_announcement(season, [])
        self.assertIn("Jan 2026", msg)
        self.assertIn("No players", msg)

    def test_build_new_season_announcement(self):
        season = self.dm.get_season_by_id(self.season_id)
        msg = self.sm.build_new_season_announcement(season)
        self.assertIn("Jan 2026", msg)

    def test_build_season_reminder(self):
        season = self.dm.get_season_by_id(self.season_id)
        self.dm.update_season_score("p1", self.season_id, points=100)
        leaderboard = self.sm.get_season_leaderboard(self.season_id)
        msg = self.sm.build_season_reminder(season, leaderboard, days_remaining=3)
        self.assertIn("3 days", msg)
        self.assertIn("Alice", msg)

    def test_build_season_reminder_one_day(self):
        season = self.dm.get_season_by_id(self.season_id)
        msg = self.sm.build_season_reminder(season, [], days_remaining=1)
        self.assertIn("1 day", msg)
        self.assertNotIn("1 days", msg)


class TestSeasonManagerIntegrationSeasonProgress(unittest.TestCase):
    """Tests for get_days_until_season_end and get_season_progress."""

    def setUp(self):
        self.db, self.dm, self.sm, _ = _make_stack()
        self.season_id = self.dm.create_season("Jan 2026", "2026-01-01", "2026-01-31")

    def tearDown(self):
        self.db.close()

    def test_days_until_end_mid_month(self):
        season = self.dm.get_season_by_id(self.season_id)
        with unittest.mock.patch.object(
            self.sm, "_today", return_value=date(2026, 1, 20)
        ):
            days = self.sm.get_days_until_season_end(season)
        self.assertEqual(days, 11)

    def test_days_until_end_on_last_day(self):
        season = self.dm.get_season_by_id(self.season_id)
        with unittest.mock.patch.object(
            self.sm, "_today", return_value=date(2026, 1, 31)
        ):
            days = self.sm.get_days_until_season_end(season)
        self.assertEqual(days, 0)

    def test_get_season_progress_mid_month(self):
        season = self.dm.get_season_by_id(self.season_id)
        with unittest.mock.patch.object(
            self.sm, "_today", return_value=date(2026, 1, 15)
        ):
            current_day, total_days = self.sm.get_season_progress(season)
        self.assertEqual(total_days, 31)
        self.assertEqual(current_day, 15)

    def test_get_season_progress_clamped(self):
        """Progress is clamped: after the season ends it shows total_days, not negative."""
        season = self.dm.get_season_by_id(self.season_id)
        with unittest.mock.patch.object(
            self.sm, "_today", return_value=date(2026, 2, 15)
        ):
            current_day, total_days = self.sm.get_season_progress(season)
        self.assertEqual(current_day, total_days)


if __name__ == "__main__":
    unittest.main()
