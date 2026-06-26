# tests/bot/managers/test_roles.py
import unittest
from unittest.mock import MagicMock
from src.core.roles import RolesGameMode
from src.core.data_manager import DataManager
from src.core.season import SeasonScore
from db.database import Database


def _make_season_score(player_id, points, season_id=1):
    """Helper to create a SeasonScore with minimal required fields."""
    return SeasonScore(player_id=player_id, season_id=season_id, points=points)


class TestRolesGameMode(unittest.TestCase):
    def setUp(self):
        # In-memory SQLite database for testing
        self.db = Database(db_path=":memory:")
        self.data_manager = DataManager(self.db)

        # Mock config — seasons disabled by default so existing tests are unaffected
        self.mock_config = MagicMock()
        self.mock_config.get.return_value = "first place"
        self.mock_config.is_seasons_enabled.return_value = False

        self.roles_game_mode = RolesGameMode(self.data_manager, self.mock_config)

        # Mock data manager methods
        self.data_manager.get_player_scores = MagicMock()
        self.data_manager.get_current_season = MagicMock()
        self.data_manager.get_season_scores = MagicMock()
        self.data_manager.clear_player_roles = MagicMock()
        self.data_manager.assign_role_to_player = MagicMock()

    def tearDown(self):
        self.db.close()

    # ── all-time score tests (seasons disabled) ───────────────────────────────

    def test_assign_roles(self):
        # Mock the data from get_player_scores
        self.data_manager.get_player_scores.return_value = [
            {"id": "1", "name": "Alice", "score": 10},
            {"id": "3", "name": "Charlie", "score": 8},
            {"id": "2", "name": "Bob", "score": 5},
        ]

        self.roles_game_mode.assign_roles()

        # Verify that clear_player_roles was called
        self.data_manager.clear_player_roles.assert_called_once()

        # Verify that assign_role_to_player was called for the top player
        self.data_manager.assign_role_to_player.assert_called_once_with(
            "1", "first place"
        )

    def test_assign_roles_tie_for_first(self):
        # Mock the data for a tie
        self.data_manager.get_player_scores.return_value = [
            {"id": "1", "name": "Alice", "score": 10},
            {"id": "2", "name": "Bob", "score": 10},
            {"id": "3", "name": "Charlie", "score": 8},
        ]

        self.roles_game_mode.assign_roles()

        # Verify clear_player_roles was called
        self.data_manager.clear_player_roles.assert_called_once()

        # Verify assign_role_to_player was called for both top players
        self.assertEqual(self.data_manager.assign_role_to_player.call_count, 2)
        self.data_manager.assign_role_to_player.assert_any_call("1", "first place")
        self.data_manager.assign_role_to_player.assert_any_call("2", "first place")

    def test_assign_roles_no_players(self):
        # Mock no players
        self.data_manager.get_player_scores.return_value = []

        self.roles_game_mode.assign_roles()

        # Verify that clear_player_roles was not called
        self.data_manager.clear_player_roles.assert_not_called()
        # Verify that assign_role_to_player was not called
        self.data_manager.assign_role_to_player.assert_not_called()

    def test_on_guess(self):
        """Test that on_guess is a no-op (just passes)."""
        # on_guess should not raise any errors and is a pass-through
        result = self.roles_game_mode.on_guess(1, "Alice", "some guess", True)
        self.assertIsNone(result)

    def test_run(self):
        """Test that run calls assign_roles."""
        self.data_manager.get_player_scores.return_value = [
            {"id": "1", "name": "Alice", "score": 10}
        ]

        self.roles_game_mode.run()

        # run() should trigger assign_roles(), which calls these methods
        self.data_manager.clear_player_roles.assert_called_once()
        self.data_manager.assign_role_to_player.assert_called_once_with(
            "1", "first place"
        )

    # ── season score tests ────────────────────────────────────────────────────

    def test_assign_roles_uses_season_scores_when_season_active(self):
        """When seasons are enabled and a season is active, use season scores."""
        self.mock_config.is_seasons_enabled.return_value = True
        mock_season = MagicMock()
        mock_season.season_id = 1
        self.data_manager.get_current_season.return_value = mock_season
        self.data_manager.get_season_scores.return_value = [
            _make_season_score("1", 500),
            _make_season_score("3", 400),
            _make_season_score("2", 300),
        ]

        self.roles_game_mode.assign_roles()

        self.data_manager.get_season_scores.assert_called_once_with(1, limit=1000)
        self.data_manager.get_player_scores.assert_not_called()
        self.data_manager.clear_player_roles.assert_called_once()
        self.data_manager.assign_role_to_player.assert_called_once_with(
            "1", "first place"
        )

    def test_assign_roles_season_tie_for_first(self):
        """Season scores: all players tied for first all receive the role."""
        self.mock_config.is_seasons_enabled.return_value = True
        mock_season = MagicMock()
        mock_season.season_id = 2
        self.data_manager.get_current_season.return_value = mock_season
        self.data_manager.get_season_scores.return_value = [
            _make_season_score("1", 500),
            _make_season_score("2", 500),
            _make_season_score("3", 200),
        ]

        self.roles_game_mode.assign_roles()

        self.assertEqual(self.data_manager.assign_role_to_player.call_count, 2)
        self.data_manager.assign_role_to_player.assert_any_call("1", "first place")
        self.data_manager.assign_role_to_player.assert_any_call("2", "first place")

    def test_assign_roles_falls_back_when_no_active_season(self):
        """When seasons are enabled but no season is active, fall back to all-time scores."""
        self.mock_config.is_seasons_enabled.return_value = True
        self.data_manager.get_current_season.return_value = None
        self.data_manager.get_player_scores.return_value = [
            {"id": "1", "name": "Alice", "score": 10},
        ]

        self.roles_game_mode.assign_roles()

        self.data_manager.get_season_scores.assert_not_called()
        self.data_manager.get_player_scores.assert_called_once()
        self.data_manager.assign_role_to_player.assert_called_once_with(
            "1", "first place"
        )

    def test_assign_roles_falls_back_when_season_scores_empty(self):
        """When seasons enabled and active but no season scores yet, fall back to all-time."""
        self.mock_config.is_seasons_enabled.return_value = True
        mock_season = MagicMock()
        mock_season.season_id = 3
        self.data_manager.get_current_season.return_value = mock_season
        self.data_manager.get_season_scores.return_value = []
        self.data_manager.get_player_scores.return_value = [
            {"id": "1", "name": "Alice", "score": 10},
        ]

        self.roles_game_mode.assign_roles()

        self.data_manager.get_player_scores.assert_called_once()
        self.data_manager.assign_role_to_player.assert_called_once_with(
            "1", "first place"
        )


class TestRolesAfterCrowdWisdomBonus(unittest.TestCase):
    """Integration tests for role assignment after crowd wisdom bonus.

    Regression tests for the bug where a sole correct solver moved from 2nd to
    1st place via the crowd wisdom bonus, but did not receive the first place
    role because roles were evaluated before the bonus was written to the DB.

    These tests use a real in-memory database so that score updates and
    role-assignment reads interact with actual SQL rather than mocks.
    """

    def setUp(self):
        self.db = Database(db_path=":memory:")
        self.data_manager = DataManager(self.db)
        self.data_manager.initialize_database()

        self.mock_config = MagicMock()
        self.mock_config.get.return_value = "first place"
        self.mock_config.is_seasons_enabled.return_value = False

        self.roles_game_mode = RolesGameMode(self.data_manager, self.mock_config)

        # Track which player IDs were assigned the role
        self.assigned_roles: list[str] = []
        original_assign = self.data_manager.assign_role_to_player

        def _track_assign(player_id, role):
            self.assigned_roles.append(player_id)
            return original_assign(player_id, role)

        self.data_manager.assign_role_to_player = _track_assign

    def tearDown(self):
        self.db.close()

    def _insert_player(self, player_id: str, name: str, score: int):
        """Insert a player directly into the DB with a given score."""
        self.db.execute_update(
            "INSERT INTO players (id, name, score) VALUES (?, ?, ?)",
            (player_id, name, score),
        )

    def _log_guess_for_player(self, player_id: str, question_id: int):
        """Log a recent guess so the player passes the 28-day activity filter."""
        self.db.execute_update(
            "INSERT INTO guesses (daily_question_id, player_id, guess_text, is_correct)"
            " VALUES (?, ?, ?, ?)",
            (question_id, player_id, "answer", 1),
        )

    def _insert_daily_question(self, question_id: int):
        """Insert a minimal daily_questions row so FK constraints are satisfied."""
        self.db.execute_update(
            "INSERT INTO daily_questions (id, question_id, sent_at)"
            " VALUES (?, ?, datetime('now'))",
            (question_id, f"q{question_id}"),
        )

    def test_crowd_wisdom_sole_solver_moves_to_first_gets_role(self):
        """A player who moves from 2nd to 1st via crowd wisdom bonus gets the role.

        Scenario: Alice is in 1st (200 pts), Bob is in 2nd (100 pts).
        Bob is the sole correct solver and receives a 100-pt crowd wisdom bonus,
        pushing him to 200 pts (tied with Alice, or above if he was close).
        After the bonus is applied, assign_roles() must give Bob the first place
        role.
        """
        self._insert_player("alice", "Alice", 200)
        self._insert_player("bob", "Bob", 100)

        self._insert_daily_question(1)
        self._log_guess_for_player("alice", 1)
        self._log_guess_for_player("bob", 1)

        # Simulate crowd wisdom: Bob earns 100 bonus points, now tied with Alice.
        # In a real tie both players get the role; this verifies Bob is included.
        self.data_manager.adjust_player_score("bob", 100)

        self.roles_game_mode.assign_roles()

        self.assertIn(
            "bob",
            self.assigned_roles,
            "Bob should receive the first place role after the crowd wisdom bonus "
            "pushes him to 1st place (200 pts, tied with Alice).",
        )

    def test_crowd_wisdom_sole_solver_clear_first_gets_role(self):
        """A player who moves clearly past the old leader via crowd wisdom gets the role."""
        self._insert_player("alice", "Alice", 200)
        self._insert_player("bob", "Bob", 100)

        self._insert_daily_question(2)
        self._log_guess_for_player("alice", 2)
        self._log_guess_for_player("bob", 2)

        # Bob gets a 150-pt crowd wisdom bonus → 250 pts, clearly above Alice.
        self.data_manager.adjust_player_score("bob", 150)

        self.roles_game_mode.assign_roles()

        self.assertIn(
            "bob",
            self.assigned_roles,
            "Bob should be the sole first-place holder (250 pts) after the crowd "
            "wisdom bonus.",
        )
        self.assertNotIn(
            "alice",
            self.assigned_roles,
            "Alice (200 pts) should NOT receive the first place role when Bob has more.",
        )


if __name__ == "__main__":
    unittest.main()
