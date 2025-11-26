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
        self.assertFalse(player.active_shield)

    def test_player_creation_with_all_values(self):
        """Test creating a Player with all values specified."""
        player = Player(
            id="456", name="Bob", score=100, answer_streak=5, active_shield=True
        )
        self.assertEqual(player.id, "456")
        self.assertEqual(player.name, "Bob")
        self.assertEqual(player.score, 100)
        self.assertEqual(player.answer_streak, 5)
        self.assertTrue(player.active_shield)

    def test_to_dict(self):
        """Test converting a Player to a dictionary."""
        player = Player(
            id="123", name="Alice", score=50, answer_streak=3, active_shield=True
        )
        data = player.to_dict()
        self.assertEqual(data["id"], "123")
        self.assertEqual(data["name"], "Alice")
        self.assertEqual(data["score"], 50)
        self.assertEqual(data["answer_streak"], 3)
        self.assertTrue(data["active_shield"])

    def test_from_dict(self):
        """Test creating a Player from a dictionary."""
        data = {
            "id": "789",
            "name": "Charlie",
            "score": 200,
            "answer_streak": 10,
            "active_shield": True,
        }
        player = Player.from_dict(data)
        self.assertEqual(player.id, "789")
        self.assertEqual(player.name, "Charlie")
        self.assertEqual(player.score, 200)
        self.assertEqual(player.answer_streak, 10)
        self.assertTrue(player.active_shield)

    def test_from_dict_with_defaults(self):
        """Test creating a Player from a dict with missing optional fields."""
        data = {"id": 999, "name": "Dave"}  # Test int id being converted to string
        player = Player.from_dict(data)
        self.assertEqual(player.id, "999")  # Should be string
        self.assertEqual(player.name, "Dave")
        self.assertEqual(player.score, 0)
        self.assertEqual(player.answer_streak, 0)
        self.assertFalse(player.active_shield)

    def test_from_dict_roundtrip(self):
        """Test that to_dict and from_dict are inverses."""
        original = Player(
            id="111", name="Eve", score=75, answer_streak=2, active_shield=False
        )
        data = original.to_dict()
        reconstructed = Player.from_dict(data)
        self.assertEqual(original.id, reconstructed.id)
        self.assertEqual(original.name, reconstructed.name)
        self.assertEqual(original.score, reconstructed.score)
        self.assertEqual(original.answer_streak, reconstructed.answer_streak)
        self.assertEqual(original.active_shield, reconstructed.active_shield)


if __name__ == "__main__":
    unittest.main()
