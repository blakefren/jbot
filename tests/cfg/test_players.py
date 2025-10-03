import unittest
from unittest.mock import patch, mock_open
from cfg.players import PlayerManager


class TestPlayerManager(unittest.TestCase):
    def test_load_players_success(self):
        """Test successful loading of players."""
        csv_data = "discord_id,firstname,lastname,phone_number,answer_streak,active_shield\n123,John,Doe,+15551234567,5,True\n456,Jane,Smith,+15557654321,0,False"
        with patch("builtins.open", mock_open(read_data=csv_data)):
            manager = PlayerManager()
            self.assertIn("123", manager.players)
            self.assertEqual(manager.players["123"]["firstname"], "John")
            self.assertEqual(manager.players["123"]["answer_streak"], 5)
            self.assertTrue(manager.players["123"]["active_shield"])
            self.assertIn("456", manager.players)
            self.assertEqual(manager.players["456"]["lastname"], "Smith")
            self.assertFalse(manager.players["456"]["active_shield"])

    def test_load_players_file_not_found(self):
        """Test FileNotFoundError during player loading."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            manager = PlayerManager()
            self.assertEqual(manager.players, {})

    def test_load_players_empty_file(self):
        """Test loading from an empty or header-only file."""
        with patch(
            "builtins.open", mock_open(read_data="discord_id,firstname,lastname\n")
        ):
            manager = PlayerManager()
            self.assertEqual(manager.players, {})

    def test_load_players_missing_discord_id(self):
        """Test that rows with missing discord_id are skipped."""
        csv_data = "discord_id,firstname,lastname\n,John,Doe\n456,Jane,Smith"
        with patch("builtins.open", mock_open(read_data=csv_data)):
            manager = PlayerManager()
            self.assertNotIn("", manager.players)
            self.assertNotIn(None, manager.players)
            self.assertIn("456", manager.players)
            self.assertEqual(len(manager.players), 1)

    def test_get_player(self):
        """Test retrieving a single player."""
        csv_data = "discord_id,firstname\n123,John"
        with patch("builtins.open", mock_open(read_data=csv_data)):
            manager = PlayerManager()
            player = manager.get_player("123")
            self.assertIsNotNone(player)
            self.assertEqual(player["firstname"], "John")
            self.assertIsNone(manager.get_player("nonexistent"))

    def test_get_all_players(self):
        """Test retrieving all players."""
        csv_data = "discord_id,firstname\n123,John\n456,Jane"
        with patch("builtins.open", mock_open(read_data=csv_data)):
            manager = PlayerManager()
            all_players = manager.get_all_players()
            self.assertEqual(len(all_players), 2)
            self.assertIn("123", all_players)
            self.assertIn("456", all_players)

    def test_save_players(self):
        """Test writing player data back to the CSV file."""
        m = mock_open()
        with patch("builtins.open", m):
            manager = PlayerManager("dummy/path/players.csv")
            m.assert_called_once_with(
                "dummy/path/players.csv", mode="r", newline="", encoding="utf-8"
            )
            m.reset_mock()
            manager.players = {
                "123": {
                    "firstname": "John",
                    "lastname": "Doe",
                    "phone_number": "",
                    "answer_streak": 1,
                    "active_shield": True,
                }
            }
            manager.save_players()
            m.assert_called_once_with(
                "dummy/path/players.csv", mode="w", newline="", encoding="utf-8"
            )

        handle = m()

        # Check that writeheader() was called
        handle.write.assert_any_call(
            "discord_id,firstname,lastname,phone_number,answer_streak,active_shield\r\n"
        )

        # Check that writerow() was called with the correct data
        handle.write.assert_any_call("123,John,Doe,,1,True\r\n")


if __name__ == "__main__":
    unittest.main()
