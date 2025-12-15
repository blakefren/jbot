import unittest
from unittest.mock import MagicMock
from src.core.powerup import PowerUpManager
from src.core.player import Player


class TestPowerUpManager(unittest.TestCase):
    def setUp(self):
        self.player_manager = MagicMock()
        self.players = {
            "1": Player(id="1", name="P1", score=100, answer_streak=3),
            "2": Player(id="2", name="P2", score=100, answer_streak=5),
            "3": Player(id="3", name="P3", score=100, answer_streak=0),
        }
        self.player_manager.get_player.side_effect = lambda pid: self.players.get(pid)

        # Mock update_score to actually update the player object for testing assertions
        def update_score(pid, amount):
            if pid in self.players:
                self.players[pid].score += amount

        self.player_manager.update_score.side_effect = update_score

        # Mock activate/deactivate shield
        def activate_shield(pid):
            if pid in self.players:
                self.players[pid].active_shield = True

        self.player_manager.activate_shield.side_effect = activate_shield

        def deactivate_shield(pid):
            if pid in self.players:
                self.players[pid].active_shield = False

        self.player_manager.deactivate_shield.side_effect = deactivate_shield

        # Mock reset_streak
        def reset_streak(pid):
            if pid in self.players:
                self.players[pid].answer_streak = 0

        self.player_manager.reset_streak.side_effect = reset_streak

    def test_disrupt_basic(self):
        manager = PowerUpManager(self.player_manager)
        msg = manager.disrupt("1", "2")
        self.assertIn("used disrupt", msg)
        self.assertEqual(self.players["1"].score, 50)
        self.assertTrue(manager._get_daily_state("2").get("under_attack"))

    def test_disrupt_with_shield(self):
        self.players["2"].active_shield = True
        manager = PowerUpManager(self.player_manager)
        msg = manager.disrupt("1", "2")
        self.assertIn("shield blocked", msg)
        self.assertFalse(self.players["2"].active_shield)
        self.assertEqual(self.players["1"].score, 50)

    def test_disrupt_not_enough_points(self):
        self.players["1"].score = 10
        manager = PowerUpManager(self.player_manager)
        msg = manager.disrupt("1", "2")
        self.assertIn("Not enough points", msg)

    def test_use_shield_basic(self):
        manager = PowerUpManager(self.player_manager)
        msg = manager.use_shield("1")
        self.assertIn("activated a shield", msg)
        self.assertTrue(self.players["1"].active_shield)
        self.assertEqual(self.players["1"].score, 75)

    def test_use_shield_already_active(self):
        self.players["1"].active_shield = True
        manager = PowerUpManager(self.player_manager)
        msg = manager.use_shield("1")
        self.assertIn("already active", msg)

    def test_use_shield_not_enough_points(self):
        self.players["1"].score = 10
        manager = PowerUpManager(self.player_manager)
        msg = manager.use_shield("1")
        self.assertIn("Not enough points", msg)

    def test_wager_points_basic(self):
        manager = PowerUpManager(self.player_manager)
        msg = manager.place_wager("1", 10)
        self.assertIn("wagered 10 points", msg)
        self.assertEqual(self.players["1"].score, 90)
        self.assertEqual(manager._get_daily_state("1")["wager"], 10)

    def test_wager_points_max_wager(self):
        manager = PowerUpManager(self.player_manager)
        msg = manager.place_wager("1", 100)
        self.assertIn("wagered 25 points", msg)  # 100//4 = 25
        self.assertEqual(self.players["1"].score, 75)
        self.assertEqual(manager._get_daily_state("1")["wager"], 25)

    def test_wager_points_invalid(self):
        manager = PowerUpManager(self.player_manager)
        msg = manager.place_wager("1", 0)
        self.assertIn("Invalid wager amount", msg)
        msg2 = manager.place_wager("1", 200)
        self.assertIn("Invalid wager amount", msg2)

    def test_resolve_wager_win(self):
        manager = PowerUpManager(self.player_manager)
        manager.place_wager("1", 20)
        msg = manager.resolve_wager("1", True)
        self.assertIn("won the wager", msg)
        self.assertEqual(manager._get_daily_state("1")["wager"], 0)

    def test_resolve_wager_lose(self):
        manager = PowerUpManager(self.player_manager)
        manager.place_wager("1", 20)
        msg = manager.resolve_wager("1", False)
        self.assertIn("lost the wager", msg)
        self.assertEqual(manager._get_daily_state("1")["wager"], 0)

    def test_resolve_wager_attack(self):
        manager = PowerUpManager(self.player_manager)
        manager._get_daily_state("1")["under_attack"] = True
        msg = manager.resolve_wager("1", False)
        self.assertIn("Streak reset", msg)
        manager._get_daily_state("1")["under_attack"] = True
        msg2 = manager.resolve_wager("1", True)
        self.assertIn("Streak preserved", msg2)

    def test_teamup_success(self):
        manager = PowerUpManager(self.player_manager)
        msg = manager.teamup("1", "2")
        self.assertEqual(self.players["1"].score, 75)
        self.assertEqual(manager._get_daily_state("1")["team_partner"], "2")

    def test_teamup_already_teamed(self):
        manager = PowerUpManager(self.player_manager)
        manager.teamup("1", "2")
        msg = manager.teamup("1", "3")
        self.assertIn("already teamed up", msg)

    def test_teamup_not_enough_points(self):
        self.players["1"].score = 10
        manager = PowerUpManager(self.player_manager)
        msg = manager.teamup("1", "2")
        self.assertIn("need at least", msg)

    def test_teamup_invalid_player(self):
        manager = PowerUpManager(self.player_manager)
        msg = manager.teamup("1", "999")
        self.assertIn("Invalid player", msg)

    def test_resolve_teamup(self):
        manager = PowerUpManager(self.player_manager)
        manager.teamup("1", "2")
        manager.resolve_teamup("1", True)
        self.assertTrue(manager._get_daily_state("1")["team_success"])
        self.assertTrue(manager._get_daily_state("2")["team_success"])

    def test_steal_success(self):
        manager = PowerUpManager(self.player_manager)
        manager._get_daily_state("2")["earned_today"] = 20
        msg = manager.steal("1", "2")
        self.assertIn("stole 10 points", msg)
        self.assertEqual(self.players["1"].score, 110)
        self.assertEqual(self.players["2"].score, 90)

    def test_steal_no_points(self):
        manager = PowerUpManager(self.player_manager)
        msg = manager.steal("1", "2")
        self.assertIn("no points to steal", msg)

    def test_steal_invalid_player(self):
        manager = PowerUpManager(self.player_manager)
        msg = manager.steal("1", "999")
        self.assertIn("Invalid player", msg)

    def test_on_guess_correct(self):
        manager = PowerUpManager(self.player_manager)
        manager.place_wager("1", 20)
        manager.on_guess("1", "P1", "guess", True)
        self.assertEqual(manager._get_daily_state("1")["wager"], 0)

    def test_on_guess_incorrect(self):
        manager = PowerUpManager(self.player_manager)
        manager.place_wager("1", 20)
        manager.on_guess("1", "P1", "guess", False)
        self.assertEqual(manager._get_daily_state("1")["wager"], 0)

    def test_disrupt_invalid_attacker(self):
        manager = PowerUpManager(self.player_manager)
        msg = manager.disrupt("999", "1")
        self.assertIn("Invalid player", msg)

    def test_disrupt_invalid_target(self):
        manager = PowerUpManager(self.player_manager)
        msg = manager.disrupt("1", "999")
        self.assertIn("Invalid player", msg)

    def test_place_wager_invalid_player(self):
        manager = PowerUpManager(self.player_manager)
        msg = manager.place_wager("999", 10)
        self.assertIn("Invalid player", msg)
