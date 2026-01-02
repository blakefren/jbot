import unittest
from unittest.mock import MagicMock
from src.core.powerup import PowerUpManager, PowerUpError
from src.core.player import Player
from datetime import date, timedelta


class TestPowerUpManagerAdditions(unittest.TestCase):
    def setUp(self):
        self.player_manager = MagicMock()
        self.data_manager = MagicMock()
        self.players = {
            "1": Player(id="1", name="P1", score=100, answer_streak=3),
            "2": Player(id="2", name="P2", score=100, answer_streak=5),
            "3": Player(id="3", name="P3", score=100, answer_streak=0),
        }
        self.player_manager.get_player.side_effect = lambda pid: self.players.get(pid)

    def test_restore_daily_state(self):
        """Test restoring daily state from simulator."""
        manager = PowerUpManager(self.player_manager, self.data_manager)

        simulated_state = {
            "wager": 50,
            "jinxed_by": "p2",
            "steal_attempt_by": None,
            "shield_active": True,
            "shield_used": False,
            "team_partner": None,
            "team_success": False,
            "silenced": False,
            "score_earned": 100,
            "bonuses": {"first_try": 20},
            "stealing_from": None,
        }

        manager.restore_daily_state("p1", simulated_state)

        state = manager._get_daily_state("p1")

        self.assertEqual(state["wager"], 50)
        self.assertEqual(state["jinxed_by"], "p2")
        self.assertTrue(state["shield_active"])
        self.assertEqual(state["earned_today"], 100)
        self.assertEqual(state["bonuses_today"], {"first_try": 20})

        # Check powerup_used_today logic
        # Shield active -> True
        self.assertTrue(state["powerup_used_today"])

    def test_restore_daily_state_powerup_used_logic(self):
        """Test powerup_used_today logic in restore."""
        manager = PowerUpManager(self.player_manager, self.data_manager)

        # Case 1: No powerups
        state1 = {
            "wager": 0,
            "shield_active": False,
            "silenced": False,
            "team_partner": None,
            "stealing_from": None,
        }
        manager.restore_daily_state("p1", state1)
        self.assertFalse(manager._get_daily_state("p1")["powerup_used_today"])

        # Case 2: Wager > 0
        state2 = {
            "wager": 10,
            "shield_active": False,
            "silenced": False,
            "team_partner": None,
            "stealing_from": None,
        }
        manager.restore_daily_state("p2", state2)
        self.assertTrue(manager._get_daily_state("p2")["powerup_used_today"])

        # Case 3: Silenced (Jinx attacker)
        state3 = {
            "wager": 0,
            "shield_active": False,
            "silenced": True,
            "team_partner": None,
            "stealing_from": None,
        }
        manager.restore_daily_state("p3", state3)
        self.assertTrue(manager._get_daily_state("p3")["powerup_used_today"])

        # Case 4: Stealing from
        state4 = {
            "wager": 0,
            "shield_active": False,
            "silenced": False,
            "team_partner": None,
            "stealing_from": "p1",
        }
        manager.restore_daily_state("p4", state4)
        self.assertTrue(manager._get_daily_state("p4")["powerup_used_today"])
