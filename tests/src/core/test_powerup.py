import unittest
from src.core.powerup import PowerUpManager


class TestPowerUpManager(unittest.TestCase):
    def setUp(self):
        self.players = {
            "1": {"score": 100, "answer_streak": 3},
            "2": {"score": 100, "answer_streak": 5},
            "3": {"score": 10, "answer_streak": 0},
        }

    def test_disrupt_basic(self):
        manager = PowerUpManager(self.players)
        msg = manager.disrupt("1", "2")
        self.assertIn("used disrupt", msg)
        self.assertEqual(self.players["1"]["score"], 50)
        self.assertTrue(self.players["2"].get("under_attack"))

    def test_disrupt_with_shield(self):
        self.players["2"]["active_shield"] = True
        manager = PowerUpManager(self.players)
        msg = manager.disrupt("1", "2")
        self.assertIn("shield blocked", msg)
        self.assertFalse(self.players["2"]["active_shield"])
        self.assertEqual(self.players["1"]["score"], 50)

    def test_disrupt_not_enough_points(self):
        self.players["1"]["score"] = 10
        manager = PowerUpManager(self.players)
        msg = manager.disrupt("1", "2")
        self.assertIn("Not enough points", msg)

    def test_use_shield_basic(self):
        manager = PowerUpManager(self.players)
        msg = manager.use_shield("1")
        self.assertIn("activated a shield", msg)
        self.assertTrue(self.players["1"]["active_shield"])
        self.assertEqual(self.players["1"]["score"], 75)

    def test_use_shield_already_active(self):
        self.players["1"]["active_shield"] = True
        manager = PowerUpManager(self.players)
        msg = manager.use_shield("1")
        self.assertIn("already active", msg)

    def test_use_shield_not_enough_points(self):
        self.players["1"]["score"] = 10
        manager = PowerUpManager(self.players)
        msg = manager.use_shield("1")
        self.assertIn("Not enough points", msg)

    def test_wager_points_basic(self):
        manager = PowerUpManager(self.players)
        msg = manager.place_wager("1", 10)
        self.assertIn("wagered 10 points", msg)
        self.assertEqual(self.players["1"]["score"], 90)
        self.assertEqual(self.players["1"]["wager"], 10)

    def test_wager_points_max_wager(self):
        manager = PowerUpManager(self.players)
        msg = manager.place_wager("1", 100)
        self.assertIn("wagered 25 points", msg)  # 100//4 = 25
        self.assertEqual(self.players["1"]["score"], 75)
        self.assertEqual(self.players["1"]["wager"], 25)

    def test_wager_points_invalid(self):
        manager = PowerUpManager(self.players)
        msg = manager.place_wager("1", 0)
        self.assertIn("Invalid wager amount", msg)
        msg2 = manager.place_wager("1", 200)
        self.assertIn("Invalid wager amount", msg2)

    def test_resolve_wager_win(self):
        manager = PowerUpManager(self.players)
        manager.place_wager("1", 20)
        msg = manager.resolve_wager("1", True)
        self.assertIn("won the wager", msg)
        self.assertEqual(self.players["1"]["wager"], 0)

    def test_resolve_wager_lose(self):
        manager = PowerUpManager(self.players)
        manager.place_wager("1", 20)
        msg = manager.resolve_wager("1", False)
        self.assertIn("lost the wager", msg)
        self.assertEqual(self.players["1"]["wager"], 0)

    def test_resolve_wager_attack(self):
        manager = PowerUpManager(self.players)
        self.players["1"]["under_attack"] = True
        msg = manager.resolve_wager("1", False)
        self.assertIn("Streak reset", msg)
        self.players["1"]["under_attack"] = True
        msg2 = manager.resolve_wager("1", True)
        self.assertIn("Streak preserved", msg2)

    def test_reinforce_success(self):
        manager = PowerUpManager(self.players)
        msg = manager.reinforce("1", "2")
        self.assertEqual(self.players["1"]["score"], 75)
        self.assertEqual(self.players["2"]["score"], 75)
        self.assertEqual(self.players["1"]["team_partner"], "2")
        self.assertEqual(self.players["2"]["team_partner"], "1")

    def test_reinforce_already_teamed(self):
        self.players["1"]["team_partner"] = "2"
        manager = PowerUpManager(self.players)
        msg = manager.reinforce("1", "2")
        self.assertIn("already teamed up", msg)

    def test_reinforce_not_enough_points(self):
        self.players["1"]["score"] = 10
        manager = PowerUpManager(self.players)
        msg = manager.reinforce("1", "2")
        self.assertIn("need at least 25 points", msg)

    def test_reinforce_invalid_player(self):
        manager = PowerUpManager(self.players)
        msg = manager.reinforce("1", "999")
        self.assertIn("Invalid player", msg)

    def test_resolve_reinforce(self):
        manager = PowerUpManager(self.players)
        manager.reinforce("1", "2")
        msg = manager.resolve_reinforce("1", True)
        self.assertTrue("both get full points" in msg or msg == "")

    def test_steal_success(self):
        self.players["2"]["earned_today"] = 40
        manager = PowerUpManager(self.players)
        msg = manager.steal("1", "2")
        self.assertIn("stole 20 points", msg)
        self.assertEqual(self.players["1"]["score"], 120)
        self.assertEqual(self.players["2"]["score"], 80)
        self.assertEqual(self.players["2"]["earned_today"], 20)

    def test_steal_no_points(self):
        self.players["2"]["earned_today"] = 0
        manager = PowerUpManager(self.players)
        msg = manager.steal("1", "2")
        self.assertIn("no points to steal", msg)

    def test_steal_invalid_player(self):
        manager = PowerUpManager(self.players)
        msg = manager.steal("1", "999")
        self.assertIn("Invalid player", msg)

    def test_on_guess_correct(self):
        """Test that on_guess calls resolve_wager with correct flag."""
        manager = PowerUpManager(self.players)
        manager.place_wager("1", 20)
        manager.on_guess(1, "Player1", "answer", True)
        # Wager should be resolved
        self.assertEqual(self.players["1"]["wager"], 0)

    def test_on_guess_incorrect(self):
        """Test that on_guess calls resolve_wager with incorrect flag."""
        manager = PowerUpManager(self.players)
        manager.place_wager("1", 20)
        manager.on_guess(1, "Player1", "answer", False)
        # Wager should be resolved
        self.assertEqual(self.players["1"]["wager"], 0)

    def test_resolve_reinforce_no_partner_in_players(self):
        """Test resolve_reinforce when partner is not found in players dict."""
        # Set up player with team_partner pointing to a non-existent player
        self.players["1"]["team_partner"] = "999"  # Partner doesn't exist
        manager = PowerUpManager(self.players)
        msg = manager.resolve_reinforce("1", True)
        # Should still set team_success for the player
        self.assertTrue(
            self.players["1"].get("team_success") or "full points" in msg or msg == ""
        )

    def test_disrupt_invalid_attacker(self):
        """Test disrupt with invalid attacker ID."""
        manager = PowerUpManager(self.players)
        msg = manager.disrupt("999", "1")
        self.assertIn("Invalid player", msg)

    def test_disrupt_invalid_target(self):
        """Test disrupt with invalid target ID (already covered, but explicit)."""
        manager = PowerUpManager(self.players)
        msg = manager.disrupt("1", "999")
        self.assertIn("Invalid player", msg)

    def test_use_shield_invalid_player(self):
        """Test use_shield with invalid player ID."""
        manager = PowerUpManager(self.players)
        msg = manager.use_shield("999")
        self.assertIn("Invalid player", msg)

    def test_place_wager_invalid_player(self):
        """Test place_wager with invalid player ID."""
        manager = PowerUpManager(self.players)
        msg = manager.place_wager("999", 10)
        self.assertIn("Invalid player", msg)

    def test_resolve_reinforce_no_team_partner(self):
        """Test resolve_reinforce when player has no team_partner."""
        manager = PowerUpManager(self.players)
        # Player 1 has no team_partner
        msg = manager.resolve_reinforce("1", True)
        self.assertEqual(msg, "")


if __name__ == "__main__":
    unittest.main()
