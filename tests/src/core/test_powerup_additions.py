import unittest
from unittest.mock import MagicMock
from src.core.powerup import PowerUpManager, PowerUpError
from src.core.player import Player
from src.core.state import DailyPlayerState
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

        simulated_state = DailyPlayerState(
            jinxed_by="p2",
            score_earned=100,
            bonuses={"first_try": 20},
        )

        manager.restore_daily_state("p1", simulated_state)

        state = manager._get_daily_state("p1")

        self.assertEqual(state.jinxed_by, "p2")
        self.assertFalse(state.is_resting)
        self.assertEqual(state.score_earned, 100)
        self.assertEqual(state.bonuses, {"first_try": 20})

    def test_restore_daily_state_powerup_used_logic(self):
        """Test powerup_used_today logic in restore."""
        manager = PowerUpManager(self.player_manager, self.data_manager)

        # Case 1: No powerups
        state1 = DailyPlayerState()
        manager.restore_daily_state("p1", state1)
        self.assertFalse(manager._get_daily_state("p1").powerup_used_today)

        # Case 2: Silenced (Jinx attacker)
        state2 = DailyPlayerState(silenced=True)
        manager.restore_daily_state("p2", state2)
        self.assertTrue(manager._get_daily_state("p2").powerup_used_today)

        # Case 3: Stealing from
        state3 = DailyPlayerState(stealing_from="p1")
        manager.restore_daily_state("p3", state3)
        self.assertTrue(manager._get_daily_state("p3").powerup_used_today)
