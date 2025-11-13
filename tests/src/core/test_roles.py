# tests/bot/managers/test_roles.py
import unittest
from unittest.mock import MagicMock
from src.core.roles import RolesGameMode
from src.core.data_manager import DataManager
from db.database import Database


class TestRolesGameMode(unittest.TestCase):
    def setUp(self):
        # In-memory SQLite database for testing
        self.db = Database(db_path=":memory:")
        self.data_manager = DataManager(self.db)

        # Mock config
        self.mock_config = MagicMock()
        self.mock_config.get.return_value = "first place"

        self.roles_game_mode = RolesGameMode(self.data_manager, self.mock_config)

        # Mock data manager methods
        self.data_manager.get_player_scores = MagicMock()
        self.data_manager.clear_player_roles = MagicMock()
        self.data_manager.assign_role_to_player = MagicMock()

    def tearDown(self):
        self.db.close()

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


if __name__ == "__main__":
    unittest.main()
