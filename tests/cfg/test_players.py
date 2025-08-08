import unittest
from unittest.mock import patch, mock_open
from cfg import players

class TestPlayers(unittest.TestCase):

    @patch("cfg.players.PLAYER_FILE_PATH", "dummy/path/players.csv")
    def test_read_players_into_dict_success(self):
        """Test successful reading of players into a dictionary."""
        csv_data = "discord_id,firstname,lastname,phone_number\n123,John,Doe,+15551234567\n456,Jane,Smith,+15557654321"
        with patch("builtins.open", mock_open(read_data=csv_data)):
            result = players.read_players_into_dict()
            expected = {
                "123": {"firstname": "John", "lastname": "Doe", "phone_number": "+15551234567"},
                "456": {"firstname": "Jane", "lastname": "Smith", "phone_number": "+15557654321"}
            }
            self.assertEqual(result, expected)

    @patch("cfg.players.PLAYER_FILE_PATH", "dummy/path/players.csv")
    def test_read_players_into_dict_file_not_found(self):
        """Test FileNotFoundError for read_players_into_dict."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            result = players.read_players_into_dict()
            self.assertEqual(result, {})

    @patch("cfg.players.PLAYER_FILE_PATH", "dummy/path/players.csv")
    def test_read_players_into_dict_empty_file(self):
        """Test read_players_into_dict with an empty file."""
        with patch("builtins.open", mock_open(read_data="")):
            result = players.read_players_into_dict()
            self.assertEqual(result, {})

    @patch("cfg.players.PLAYER_FILE_PATH", "dummy/path/players.csv")
    def test_read_players_into_dict_missing_discord_id(self):
        """Test that rows with missing discord_id are skipped."""
        csv_data = "discord_id,firstname,lastname,phone_number\n,John,Doe,+15551234567\n456,Jane,Smith,+15557654321"
        with patch("builtins.open", mock_open(read_data=csv_data)):
            result = players.read_players_into_dict()
            expected = {
                "456": {"firstname": "Jane", "lastname": "Smith", "phone_number": "+15557654321"}
            }
            self.assertEqual(result, expected)

    @patch("cfg.players.PLAYER_FILE_PATH", "dummy/path/players.csv")
    def test_read_and_validate_contacts_success(self):
        """Test successful reading and validation of contacts."""
        csv_data = "firstname,lastname,phone_number,discord_id\nJohn,Doe,+15551234567,123\nJane,Smith,+15557654321,456"
        with patch("builtins.open", mock_open(read_data=csv_data)):
            result = players.read_and_validate_contacts()
            expected = [
                {"firstname": "John", "lastname": "Doe", "phone_number": "+15551234567", "discord_id": "123"},
                {"firstname": "Jane", "lastname": "Smith", "phone_number": "+15557654321", "discord_id": "456"}
            ]
            self.assertEqual(result, expected)

    @patch("cfg.players.PLAYER_FILE_PATH", "dummy/path/players.csv")
    def test_read_and_validate_contacts_file_not_found(self):
        """Test FileNotFoundError for read_and_validate_contacts."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            result = players.read_and_validate_contacts()
            self.assertEqual(result, [])

    @patch("cfg.players.PLAYER_FILE_PATH", "dummy/path/players.csv")
    def test_read_and_validate_contacts_missing_headers(self):
        """Test CSV with missing required headers."""
        csv_data = "firstname,lastname\nJohn,Doe"
        with patch("builtins.open", mock_open(read_data=csv_data)):
            result = players.read_and_validate_contacts()
            self.assertEqual(result, [])

    @patch("cfg.players.PLAYER_FILE_PATH", "dummy/path/players.csv")
    def test_read_and_validate_contacts_invalid_phone(self):
        """Test validation of rows with invalid phone numbers."""
        csv_data = "firstname,lastname,phone_number,discord_id\nJohn,Doe,555-1234,123\nJane,Smith,+15557654321,456"
        with patch("builtins.open", mock_open(read_data=csv_data)):
            result = players.read_and_validate_contacts()
            expected = [
                {"firstname": "Jane", "lastname": "Smith", "phone_number": "+15557654321", "discord_id": "456"}
            ]
            self.assertEqual(result, expected)

    @patch("cfg.players.PLAYER_FILE_PATH", "dummy/path/players.csv")
    def test_read_and_validate_contacts_sanitized_names(self):
        """Test sanitization of names with non-alphabetic characters."""
        csv_data = "firstname,lastname,phone_number,discord_id\nJohn123,Doe-Smith,+15551234567,123"
        with patch("builtins.open", mock_open(read_data=csv_data)):
            result = players.read_and_validate_contacts()
            expected = [
                {"firstname": "John", "lastname": "DoeSmith", "phone_number": "+15551234567", "discord_id": "123"}
            ]
            self.assertEqual(result, expected)

    @patch("cfg.players.PLAYER_FILE_PATH", "dummy/path/players.csv")
    def test_read_and_validate_contacts_missing_names(self):
        """Test handling of missing first and last names."""
        csv_data = "firstname,lastname,phone_number,discord_id\n,Smith,+15551234567,123\nJohn,,+15557654321,456"
        with patch("builtins.open", mock_open(read_data=csv_data)):
            result = players.read_and_validate_contacts()
            expected = [
                {"firstname": "Unknown", "lastname": "Smith", "phone_number": "+15551234567", "discord_id": "123"},
                {"firstname": "John", "lastname": "Unknown", "phone_number": "+15557654321", "discord_id": "456"}
            ]
            self.assertEqual(result, expected)

if __name__ == "__main__":
    unittest.main()
