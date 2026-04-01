import unittest
from unittest.mock import MagicMock
from src.core.player_manager import PlayerManager
from src.core.player import Player
from src.core.data_manager import DataManager


class TestPlayerManager(unittest.TestCase):
    def setUp(self):
        self.mock_data_manager = MagicMock(spec=DataManager)
        self.manager = PlayerManager(self.mock_data_manager)

    def test_get_player(self):
        """Test retrieving a single player via DataManager."""
        expected_player = Player(
            id="123",
            name="John Doe",
            score=10,
            answer_streak=5,
            pending_rest_multiplier=0.0,
        )
        self.mock_data_manager.get_player.return_value = expected_player

        player = self.manager.get_player("123")

        self.mock_data_manager.get_player.assert_called_with("123")
        self.assertEqual(player, expected_player)

    def test_get_player_with_int_id(self):
        """Test retrieving a player using an integer ID (should be normalized)."""
        self.manager.get_player(123)
        self.mock_data_manager.get_player.assert_called_with("123")

    def test_get_all_players(self):
        """Test retrieving all players via DataManager."""
        expected_players = {
            "123": Player(id="123", name="John Doe"),
            "456": Player(id="456", name="Jane Smith"),
        }
        self.mock_data_manager.get_all_players.return_value = expected_players

        all_players = self.manager.get_all_players()

        self.mock_data_manager.get_all_players.assert_called_once()
        self.assertEqual(all_players, expected_players)

    def test_update_score(self):
        """Test updating a player's score."""
        self.manager.update_score("123", 50)
        self.mock_data_manager.adjust_player_score.assert_called_with("123", 50)

    def test_set_name_existing_player(self):
        """Test updating an existing player's name."""
        self.mock_data_manager.get_player.return_value = Player(
            id="123", name="Old Name"
        )

        self.manager.set_name("123", "New Name")

        self.mock_data_manager.update_player_name.assert_called_with("123", "New Name")
        self.mock_data_manager.create_player.assert_not_called()

    def test_set_name_new_player(self):
        """Test setting name creates a new player if missing."""
        self.mock_data_manager.get_player.return_value = None

        self.manager.set_name("456", "New Player")

        self.mock_data_manager.create_player.assert_called_with("456", "New Player")
        self.mock_data_manager.update_player_name.assert_not_called()

    def test_increment_streak_existing_player(self):
        """Test incrementing streak for an existing player."""
        self.mock_data_manager.get_player.return_value = Player(
            id="123", name="Test Player"
        )

        self.manager.increment_streak("123")

        self.mock_data_manager.increment_streak.assert_called_with("123")
        self.mock_data_manager.create_player.assert_not_called()

    def test_increment_streak_new_player(self):
        """Test incrementing streak creates a new player if missing."""
        self.mock_data_manager.get_player.return_value = None

        self.manager.increment_streak("456", "New Player")

        self.mock_data_manager.create_player.assert_called_with("456", "New Player")
        self.mock_data_manager.increment_streak.assert_called_with("456")

    def test_reset_streak(self):
        """Test resetting a player's streak."""
        self.manager.reset_streak("123")
        self.mock_data_manager.reset_streak.assert_called_with("123")

    def test_get_or_create_player_existing(self):
        """Test get_or_create_player with an existing player."""
        existing_player = Player(id="123", name="Old Name")
        self.mock_data_manager.get_player.return_value = existing_player

        player = self.manager.get_or_create_player("123", "New Name")

        self.mock_data_manager.update_player_name.assert_called_with("123", "New Name")
        self.assertEqual(player.name, "New Name")

    def test_get_or_create_player_existing_same_name(self):
        """Test get_or_create_player with existing player and same name."""
        existing_player = Player(id="123", name="Same Name")
        self.mock_data_manager.get_player.return_value = existing_player

        player = self.manager.get_or_create_player("123", "Same Name")

        self.mock_data_manager.update_player_name.assert_not_called()
        self.assertEqual(player.name, "Same Name")

    def test_get_or_create_player_new(self):
        """Test get_or_create_player creates a new player."""
        # First call returns None (not found), second call returns created player
        new_player = Player(id="456", name="New Player")
        self.mock_data_manager.get_player.side_effect = [None, new_player]

        player = self.manager.get_or_create_player("456", "New Player")

        self.mock_data_manager.create_player.assert_called_with("456", "New Player")
        self.assertEqual(player, new_player)

    def test_set_streak(self):
        """Test setting a player's streak to a specific value."""
        self.manager.set_streak("123", 10)
        self.mock_data_manager.set_streak.assert_called_with("123", 10)

    def test_adjust_season_score_with_active_season(self):
        """adjust_season_score updates both players.season_score and season_scores.points."""
        from src.core.season import Season
        from datetime import date

        active_season = Season(
            7, "April 2026", date(2026, 4, 1), date(2026, 4, 30), True
        )
        self.mock_data_manager.get_current_season.return_value = active_season

        self.manager.adjust_season_score("123", 50)

        self.mock_data_manager.increment_lifetime_stat.assert_called_once_with(
            "123", "season_score", 50
        )
        self.mock_data_manager.increment_season_stat.assert_called_once_with(
            "123", 7, "points", 50
        )

    def test_adjust_season_score_no_active_season(self):
        """adjust_season_score is a no-op when no season is active."""
        self.mock_data_manager.get_current_season.return_value = None

        self.manager.adjust_season_score("123", 50)

        self.mock_data_manager.increment_lifetime_stat.assert_not_called()
        self.mock_data_manager.increment_season_stat.assert_not_called()

    def test_adjust_season_score_normalizes_id(self):
        """adjust_season_score normalizes integer IDs to strings."""
        from src.core.season import Season
        from datetime import date

        active_season = Season(3, "Test", date(2026, 1, 1), date(2026, 1, 31), True)
        self.mock_data_manager.get_current_season.return_value = active_season

        self.manager.adjust_season_score(123, 10)

        self.mock_data_manager.increment_lifetime_stat.assert_called_once_with(
            "123", "season_score", 10
        )

    def test_normalize_id_with_none(self):
        """Test _normalize_id handles None gracefully."""
        result = self.manager._normalize_id(None)
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
