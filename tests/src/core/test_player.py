import unittest
from src.core.player import Player


class TestPlayer(unittest.TestCase):
    def test_player_creation(self):
        """Test creating a Player with default values."""
        player = Player(id="123", name="Alice")
        self.assertEqual(player.id, "123")
        self.assertEqual(player.name, "Alice")
        self.assertEqual(player.score, 0)
        self.assertEqual(player.answer_streak, 0)
        self.assertEqual(player.pending_rest_multiplier, 0.0)

    def test_player_creation_with_all_values(self):
        """Test creating a Player with all values specified."""
        player = Player(
            id="456",
            name="Bob",
            score=100,
            answer_streak=5,
            pending_rest_multiplier=1.2,
        )
        self.assertEqual(player.id, "456")
        self.assertEqual(player.name, "Bob")
        self.assertEqual(player.score, 100)
        self.assertEqual(player.answer_streak, 5)
        self.assertEqual(player.pending_rest_multiplier, 1.2)


if __name__ == "__main__":
    unittest.main()
