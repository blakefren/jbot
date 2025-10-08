import unittest
from unittest.mock import patch, MagicMock
from src.cfg.players import PlayerManager
from database.database import Database


class TestPlayerManager(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock(spec=Database)

    def test_load_players_success(self):
        """Test successful loading of players."""
        self.mock_db.execute_query.return_value = [
            {"id": "123", "name": "John Doe", "score": 10, "answer_streak": 5, "active_shield": 1},
            {"id": "456", "name": "Jane Smith", "score": 20, "answer_streak": 0, "active_shield": 0},
        ]
        manager = PlayerManager(self.mock_db)
        self.assertIn("123", manager.players)
        self.assertEqual(manager.players["123"]["name"], "John Doe")
        self.assertEqual(manager.players["123"]["score"], 10)
        self.assertEqual(manager.players["123"]["answer_streak"], 5)
        self.assertTrue(manager.players["123"]["active_shield"])
        self.assertIn("456", manager.players)
        self.assertEqual(manager.players["456"]["name"], "Jane Smith")
        self.assertEqual(manager.players["456"]["score"], 20)
        self.assertFalse(manager.players["456"]["active_shield"])

    def test_load_players_empty_db(self):
        """Test loading from an empty database."""
        self.mock_db.execute_query.return_value = []
        manager = PlayerManager(self.mock_db)
        self.assertEqual(manager.players, {})

    def test_get_player(self):
        """Test retrieving a single player."""
        self.mock_db.execute_query.return_value = [
            {"id": "123", "name": "John Doe", "score": 10, "answer_streak": 5, "active_shield": 1}
        ]
        manager = PlayerManager(self.mock_db)
        player = manager.get_player("123")
        self.assertIsNotNone(player)
        self.assertEqual(player["name"], "John Doe")
        self.assertEqual(player["score"], 10)
        self.assertIsNone(manager.get_player("nonexistent"))

    def test_get_all_players(self):
        """Test retrieving all players."""
        self.mock_db.execute_query.return_value = [
            {"id": "123", "name": "John Doe", "score": 10, "answer_streak": 5, "active_shield": 1},
            {"id": "456", "name": "Jane Smith", "score": 20, "answer_streak": 0, "active_shield": 0},
        ]
        manager = PlayerManager(self.mock_db)
        all_players = manager.get_all_players()
        self.assertEqual(len(all_players), 2)
        self.assertIn("123", all_players)
        self.assertIn("456", all_players)

    def test_save_players(self):
        """Test writing player data back to the database."""
        manager = PlayerManager(self.mock_db)
        manager.players = {
            "123": {
                "name": "John Doe",
                "score": 15,
                "answer_streak": 1,
                "active_shield": True,
            }
        }
        manager.save_players()

        self.mock_db.execute_update.assert_called_once()
        call_args = self.mock_db.execute_update.call_args
        query = call_args[0][0]
        params = call_args[0][1]

        self.assertIn("INSERT INTO players", query)
        self.assertEqual(params[0], "123")
        self.assertEqual(params[1], "John Doe")
        self.assertEqual(params[2], 15)


if __name__ == "__main__":
    unittest.main()
