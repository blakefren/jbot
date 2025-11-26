import unittest
from unittest.mock import MagicMock
from src.core.player_manager import PlayerManager
from src.core.player import Player
from src.core.data_manager import DataManager


class TestPlayerManager(unittest.TestCase):
    def setUp(self):
        self.mock_data_manager = MagicMock(spec=DataManager)

    def test_load_players_success(self):
        """Test successful loading of players via DataManager."""
        self.mock_data_manager.load_players.return_value = {
            "123": Player(
                id="123", name="John Doe", score=10, answer_streak=5, active_shield=True
            ),
            "456": Player(
                id="456",
                name="Jane Smith",
                score=20,
                answer_streak=0,
                active_shield=False,
            ),
        }
        manager = PlayerManager(self.mock_data_manager)
        self.assertIn("123", manager.players)
        self.assertEqual(manager.players["123"].name, "John Doe")
        self.assertEqual(manager.players["123"].score, 10)
        self.assertEqual(manager.players["123"].answer_streak, 5)
        self.assertTrue(manager.players["123"].active_shield)
        self.assertIn("456", manager.players)
        self.assertEqual(manager.players["456"].name, "Jane Smith")
        self.assertEqual(manager.players["456"].score, 20)
        self.assertFalse(manager.players["456"].active_shield)

    def test_load_players_empty_db(self):
        """Test loading from an empty database via DataManager."""
        self.mock_data_manager.load_players.return_value = {}
        manager = PlayerManager(self.mock_data_manager)
        self.assertEqual(manager.players, {})

    def test_get_player(self):
        """Test retrieving a single player via DataManager."""
        self.mock_data_manager.load_players.return_value = {
            "123": Player(
                id="123", name="John Doe", score=10, answer_streak=5, active_shield=True
            )
        }
        manager = PlayerManager(self.mock_data_manager)
        player = manager.get_player("123")
        self.assertIsNotNone(player)
        self.assertEqual(player.name, "John Doe")
        self.assertEqual(player.score, 10)
        self.assertIsNone(manager.get_player("nonexistent"))

    def test_get_player_with_int_id(self):
        """Test retrieving a player using an integer ID (should be normalized)."""
        self.mock_data_manager.load_players.return_value = {
            "123": Player(id="123", name="John Doe", score=10)
        }
        manager = PlayerManager(self.mock_data_manager)
        # Pass an int instead of string
        player = manager.get_player(123)
        self.assertIsNotNone(player)
        self.assertEqual(player.name, "John Doe")

    def test_get_all_players(self):
        """Test retrieving all players via DataManager."""
        self.mock_data_manager.load_players.return_value = {
            "123": Player(
                id="123", name="John Doe", score=10, answer_streak=5, active_shield=True
            ),
            "456": Player(
                id="456",
                name="Jane Smith",
                score=20,
                answer_streak=0,
                active_shield=False,
            ),
        }
        manager = PlayerManager(self.mock_data_manager)
        all_players = manager.get_all_players()
        self.assertEqual(len(all_players), 2)
        self.assertIn("123", all_players)
        self.assertIn("456", all_players)

    def test_save_players(self):
        """Test writing player data back to the database via DataManager."""
        manager = PlayerManager(self.mock_data_manager)
        from src.core.player import Player

        manager.players = {
            "123": Player(
                id="123", name="John Doe", score=15, answer_streak=1, active_shield=True
            )
        }
        manager.save_players()
        self.mock_data_manager.save_players.assert_called_once_with(manager.players)

    def test_update_score(self):
        """Test updating a player's score."""
        players_dict = {"123": Player(id="123", name="Test Player", score=100)}
        self.mock_data_manager.load_players.return_value = players_dict
        manager = PlayerManager(self.mock_data_manager)

        manager.update_score("123", 50)
        self.assertEqual(manager.get_player("123").score, 150)
        self.mock_data_manager.save_players.assert_called_with(manager.players)

    def test_update_score_nonexistent_player(self):
        """Test updating score for a player that doesn't exist."""
        self.mock_data_manager.load_players.return_value = {}
        manager = PlayerManager(self.mock_data_manager)

        # Should not raise an error, just do nothing
        manager.update_score("nonexistent", 50)
        self.mock_data_manager.save_players.assert_not_called()

    def test_set_name_existing_player(self):
        """Test updating an existing player's name."""
        players_dict = {"123": Player(id="123", name="Old Name", score=100)}
        self.mock_data_manager.load_players.return_value = players_dict
        manager = PlayerManager(self.mock_data_manager)

        manager.set_name("123", "New Name")
        self.assertEqual(manager.get_player("123").name, "New Name")
        self.mock_data_manager.save_players.assert_called_with(manager.players)

    def test_set_name_new_player(self):
        """Test setting name creates a new player if missing."""
        self.mock_data_manager.load_players.return_value = {}
        manager = PlayerManager(self.mock_data_manager)

        manager.set_name("456", "New Player")
        self.assertIn("456", manager.players)
        self.assertEqual(manager.players["456"].name, "New Player")
        self.mock_data_manager.save_players.assert_called_with(manager.players)

    def test_increment_streak_existing_player(self):
        """Test incrementing streak for an existing player."""
        players_dict = {"123": Player(id="123", name="Test Player", answer_streak=3)}
        self.mock_data_manager.load_players.return_value = players_dict
        manager = PlayerManager(self.mock_data_manager)

        manager.increment_streak("123")
        self.assertEqual(manager.get_player("123").answer_streak, 4)
        self.mock_data_manager.save_players.assert_called_with(manager.players)

    def test_increment_streak_new_player(self):
        """Test incrementing streak creates a new player if missing."""
        self.mock_data_manager.load_players.return_value = {}
        manager = PlayerManager(self.mock_data_manager)

        manager.increment_streak("456", "New Player")
        self.assertIn("456", manager.players)
        self.assertEqual(manager.players["456"].answer_streak, 1)
        self.assertEqual(manager.players["456"].name, "New Player")
        self.mock_data_manager.save_players.assert_called_with(manager.players)

    def test_increment_streak_new_player_no_name(self):
        """Test incrementing streak for new player without providing name."""
        self.mock_data_manager.load_players.return_value = {}
        manager = PlayerManager(self.mock_data_manager)

        manager.increment_streak("456")
        self.assertIn("456", manager.players)
        self.assertEqual(manager.players["456"].answer_streak, 1)
        self.assertEqual(manager.players["456"].name, "456")  # Uses ID as name
        self.mock_data_manager.save_players.assert_called_with(manager.players)

    def test_reset_streak(self):
        """Test resetting a player's streak."""
        players_dict = {"123": Player(id="123", name="Test Player", answer_streak=5)}
        self.mock_data_manager.load_players.return_value = players_dict
        manager = PlayerManager(self.mock_data_manager)

        manager.reset_streak("123")
        self.assertEqual(manager.get_player("123").answer_streak, 0)
        self.mock_data_manager.save_players.assert_called_with(manager.players)

    def test_reset_streak_already_zero(self):
        """Test resetting streak when already zero doesn't trigger save."""
        players_dict = {"123": Player(id="123", name="Test Player", answer_streak=0)}
        self.mock_data_manager.load_players.return_value = players_dict
        manager = PlayerManager(self.mock_data_manager)

        manager.reset_streak("123")
        self.mock_data_manager.save_players.assert_not_called()

    def test_reset_streak_nonexistent_player(self):
        """Test resetting streak for nonexistent player does nothing."""
        self.mock_data_manager.load_players.return_value = {}
        manager = PlayerManager(self.mock_data_manager)

        manager.reset_streak("nonexistent")
        self.mock_data_manager.save_players.assert_not_called()

    def test_activate_shield(self):
        """Test activating a player's shield."""
        players_dict = {
            "123": Player(id="123", name="Test Player", active_shield=False)
        }
        self.mock_data_manager.load_players.return_value = players_dict
        manager = PlayerManager(self.mock_data_manager)

        manager.activate_shield("123")
        self.assertTrue(manager.get_player("123").active_shield)
        self.mock_data_manager.save_players.assert_called_with(manager.players)

    def test_activate_shield_already_active(self):
        """Test activating shield when already active doesn't trigger save."""
        players_dict = {"123": Player(id="123", name="Test Player", active_shield=True)}
        self.mock_data_manager.load_players.return_value = players_dict
        manager = PlayerManager(self.mock_data_manager)

        manager.activate_shield("123")
        self.mock_data_manager.save_players.assert_not_called()

    def test_activate_shield_nonexistent_player(self):
        """Test activating shield for nonexistent player does nothing."""
        self.mock_data_manager.load_players.return_value = {}
        manager = PlayerManager(self.mock_data_manager)

        manager.activate_shield("nonexistent")
        self.mock_data_manager.save_players.assert_not_called()

    def test_deactivate_shield(self):
        """Test deactivating a player's shield."""
        players_dict = {"123": Player(id="123", name="Test Player", active_shield=True)}
        self.mock_data_manager.load_players.return_value = players_dict
        manager = PlayerManager(self.mock_data_manager)

        manager.deactivate_shield("123")
        self.assertFalse(manager.get_player("123").active_shield)
        self.mock_data_manager.save_players.assert_called_with(manager.players)

    def test_deactivate_shield_already_inactive(self):
        """Test deactivating shield when already inactive doesn't trigger save."""
        players_dict = {
            "123": Player(id="123", name="Test Player", active_shield=False)
        }
        self.mock_data_manager.load_players.return_value = players_dict
        manager = PlayerManager(self.mock_data_manager)

        manager.deactivate_shield("123")
        self.mock_data_manager.save_players.assert_not_called()

    def test_deactivate_shield_nonexistent_player(self):
        """Test deactivating shield for nonexistent player does nothing."""
        self.mock_data_manager.load_players.return_value = {}
        manager = PlayerManager(self.mock_data_manager)

        manager.deactivate_shield("nonexistent")
        self.mock_data_manager.save_players.assert_not_called()

    def test_get_or_create_player_existing(self):
        """Test get_or_create_player with an existing player."""
        players_dict = {"123": Player(id="123", name="Old Name", score=100)}
        self.mock_data_manager.load_players.return_value = players_dict
        manager = PlayerManager(self.mock_data_manager)

        player = manager.get_or_create_player("123", "New Name")
        self.assertEqual(player.name, "New Name")  # Name should be updated
        self.assertEqual(player.score, 100)  # Score unchanged
        self.mock_data_manager.save_players.assert_called_with(manager.players)

    def test_get_or_create_player_existing_same_name(self):
        """Test get_or_create_player with existing player and same name."""
        players_dict = {"123": Player(id="123", name="Same Name", score=100)}
        self.mock_data_manager.load_players.return_value = players_dict
        manager = PlayerManager(self.mock_data_manager)

        player = manager.get_or_create_player("123", "Same Name")
        self.assertEqual(player.name, "Same Name")
        # Should not save when name is the same
        self.mock_data_manager.save_players.assert_not_called()

    def test_get_or_create_player_new(self):
        """Test get_or_create_player creates a new player."""
        self.mock_data_manager.load_players.return_value = {}
        manager = PlayerManager(self.mock_data_manager)

        player = manager.get_or_create_player("456", "New Player")
        self.assertEqual(player.id, "456")
        self.assertEqual(player.name, "New Player")
        self.assertEqual(player.score, 0)
        self.assertIn("456", manager.players)
        self.mock_data_manager.save_players.assert_called_with(manager.players)

    def test_refund_score(self):
        """Test refunding a player's score and saving via DataManager."""
        from src.core.player import Player

        players_dict = {
            "123": Player(
                id="123",
                name="Test Player",
                score=100,
                answer_streak=0,
                active_shield=False,
            )
        }
        self.mock_data_manager.load_players.return_value = players_dict
        manager = PlayerManager(self.mock_data_manager)

        # Initial score
        self.assertEqual(manager.get_player("123").score, 100)

        # Refund
        manager.refund_score("123", 50)

        # Check score in memory
        self.assertEqual(manager.get_player("123").score, 150)

        # Check that DataManager.save_players was called with updated players
        self.mock_data_manager.save_players.assert_called_with(manager.players)

    def test_refund_score_nonexistent_player(self):
        """Test refunding score for nonexistent player does nothing."""
        self.mock_data_manager.load_players.return_value = {}
        manager = PlayerManager(self.mock_data_manager)

        manager.refund_score("nonexistent", 50)
        self.mock_data_manager.save_players.assert_not_called()

    def test_refund_score_multiple(self):
        """Test that multiple refunds accumulate correctly."""
        from src.core.player import Player

        players_dict = {
            "123": Player(
                id="123",
                name="Test Player",
                score=100,
                answer_streak=0,
                active_shield=False,
            )
        }
        self.mock_data_manager.load_players.return_value = players_dict
        manager = PlayerManager(self.mock_data_manager)

        # First refund
        manager.refund_score("123", 50)
        self.assertEqual(manager.get_player("123").score, 150)

        # Second refund
        manager.refund_score("123", 25)
        self.assertEqual(manager.get_player("123").score, 175)

        # Verify the final score in the "database"
        final_player_state = manager.get_player("123")
        self.assertEqual(final_player_state.score, 175)

    def test_reload_players(self):
        """Test reloading players from the database."""
        initial_players = {"123": Player(id="123", name="Initial", score=0)}
        self.mock_data_manager.load_players.return_value = initial_players
        manager = PlayerManager(self.mock_data_manager)

        # Change the mock to return different data
        updated_players = {"123": Player(id="123", name="Updated", score=999)}
        self.mock_data_manager.load_players.return_value = updated_players

        manager.reload_players()

        self.assertEqual(manager.get_player("123").name, "Updated")
        self.assertEqual(manager.get_player("123").score, 999)

    def test_normalize_id_with_none(self):
        """Test _normalize_id handles None gracefully."""
        self.mock_data_manager.load_players.return_value = {}
        manager = PlayerManager(self.mock_data_manager)

        result = manager._normalize_id(None)
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
