import unittest
from unittest.mock import patch, MagicMock
from src.cfg.players import PlayerManager
from db.database import Database


class TestPlayerManager(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock(spec=Database)
        self.mock_data_manager = MagicMock()
        patcher = patch('src.cfg.players.DataManager', return_value=self.mock_data_manager)
        self.addCleanup(patcher.stop)
        self.mock_data_manager_class = patcher.start()

    def test_load_players_success(self):
        """Test successful loading of players via DataManager."""
        self.mock_data_manager.load_players.return_value = {
            "123": {"name": "John Doe", "score": 10, "answer_streak": 5, "active_shield": True},
            "456": {"name": "Jane Smith", "score": 20, "answer_streak": 0, "active_shield": False},
        }
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
        """Test loading from an empty database via DataManager."""
        self.mock_data_manager.load_players.return_value = {}
        manager = PlayerManager(self.mock_db)
        self.assertEqual(manager.players, {})

    def test_get_player(self):
        """Test retrieving a single player via DataManager."""
        self.mock_data_manager.load_players.return_value = {
            "123": {"name": "John Doe", "score": 10, "answer_streak": 5, "active_shield": True}
        }
        manager = PlayerManager(self.mock_db)
        player = manager.get_player("123")
        self.assertIsNotNone(player)
        self.assertEqual(player["name"], "John Doe")
        self.assertEqual(player["score"], 10)
        self.assertIsNone(manager.get_player("nonexistent"))

    def test_get_all_players(self):
        """Test retrieving all players via DataManager."""
        self.mock_data_manager.load_players.return_value = {
            "123": {"name": "John Doe", "score": 10, "answer_streak": 5, "active_shield": True},
            "456": {"name": "Jane Smith", "score": 20, "answer_streak": 0, "active_shield": False},
        }
        manager = PlayerManager(self.mock_db)
        all_players = manager.get_all_players()
        self.assertEqual(len(all_players), 2)
        self.assertIn("123", all_players)
        self.assertIn("456", all_players)

    def test_save_players(self):
        """Test writing player data back to the database via DataManager."""
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

        self.mock_data_manager.save_players.assert_called_once_with(manager.players)

    def test_refund_score(self):
        """Test refunding a player's score and saving via DataManager."""
        with patch('src.cfg.players.DataManager') as MockDataManager:
            players_dict = {
                "123": {"name": "Test Player", "score": 100, "answer_streak": 0, "active_shield": False}
            }
            instance = MockDataManager.return_value
            instance.load_players.return_value = players_dict
            manager = PlayerManager(self.mock_db)

            # Initial score
            self.assertEqual(manager.get_player("123")["score"], 100)

            # Refund
            manager.refund_score("123", 50)

            # Check score in memory
            self.assertEqual(manager.get_player("123")["score"], 150)

            # Check that DataManager.save_players was called with updated players
            instance.save_players.assert_called_once_with(manager.players)

    def test_refund_score_multiple(self):
        """Test that multiple refunds accumulate correctly."""
        with patch('src.cfg.players.DataManager') as MockDataManager:
            players_dict = {
                "123": {"name": "Test Player", "score": 100, "answer_streak": 0, "active_shield": False}
            }
            instance = MockDataManager.return_value
            instance.load_players.return_value = players_dict
            manager = PlayerManager(self.mock_db)

            # First refund
            manager.refund_score("123", 50)
            self.assertEqual(manager.get_player("123")["score"], 150)

            # Second refund
            manager.refund_score("123", 25)
            self.assertEqual(manager.get_player("123")["score"], 175)

            # Verify the final score in the "database"
            final_player_state = manager.get_player("123")
            self.assertEqual(final_player_state["score"], 175)


if __name__ == "__main__":
    unittest.main()
