import unittest
from unittest.mock import patch, MagicMock
from src.cfg.players import PlayerManager
from db.database import Database


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

    def test_refund_score(self):
        """Test refunding a player's score."""
        self.mock_db.execute_query.return_value = [
            {"id": "123", "name": "Test Player", "score": 100, "answer_streak": 0, "active_shield": 0}
        ]
        manager = PlayerManager(self.mock_db)

        # Initial score
        self.assertEqual(manager.get_player("123")["score"], 100)

        # Refund
        manager.refund_score("123", 50)

        # Check score in memory
        self.assertEqual(manager.get_player("123")["score"], 150)

        # Check that save_players was called, which calls execute_update
        self.mock_db.execute_update.assert_called()

        # Verify the correct data was passed to the DB
        call_args = self.mock_db.execute_update.call_args
        query = call_args[0][0]
        params = call_args[0][1]

        self.assertIn("INSERT INTO players", query)
        self.assertEqual(params[0], "123")  # id
        self.assertEqual(params[2], 150)  # score

    def test_refund_score_multiple(self):
        """Test that multiple refunds accumulate correctly."""
        # We need to mock the load to happen only once.
        self.mock_db.execute_query.return_value = [
            {"id": "123", "name": "Test Player", "score": 100, "answer_streak": 0, "active_shield": 0}
        ]
        manager = PlayerManager(self.mock_db)
        # Now, we change the mock so it reflects the updates from save_players
        def side_effect(*args, **kwargs):
            # This simulates the database being updated
            if "UPDATE" in args[0] or "INSERT" in args[0]:
                updated_score = args[1][2]
                self.mock_db.execute_query.return_value = [
                    {"id": "123", "name": "Test Player", "score": updated_score, "answer_streak": 0, "active_shield": 0}
                ]
        self.mock_db.execute_update.side_effect = side_effect

        # First refund
        manager.refund_score("123", 50)
        self.assertEqual(manager.get_player("123")["score"], 150)
        # After the refund, the manager reloads players. We need to simulate this.
        manager.players = manager._load_players()

        # Second refund
        manager.refund_score("123", 25)
        self.assertEqual(manager.get_player("123")["score"], 175)
        manager.players = manager._load_players()

        # Verify the final score in the "database"
        final_player_state = manager.get_player("123")
        self.assertEqual(final_player_state["score"], 175)


if __name__ == "__main__":
    unittest.main()
