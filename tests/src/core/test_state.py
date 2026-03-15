import unittest
from src.core.state import DailyPlayerState


class TestDailyPlayerState(unittest.TestCase):
    def test_initialization(self):
        """Test that the state initializes with default values."""
        state = DailyPlayerState()
        self.assertEqual(state.score_earned, 0)
        self.assertFalse(state.is_resting)
        self.assertFalse(state.powerup_used_today)
        self.assertEqual(state.bonuses, {})

    def test_aliases(self):
        """Test that alias properties work correctly."""
        state = DailyPlayerState()
        state.score_earned = 100
        state.bonuses = {"streak": 10}

        self.assertEqual(state.earned_today, 100)
        self.assertEqual(state.bonuses_today, {"streak": 10})

        # Test setter alias
        state.bonuses_today = {"fastest": 5}
        self.assertEqual(state.bonuses, {"fastest": 5})

    def test_powerup_used_today_resting(self):
        state = DailyPlayerState()
        state.is_resting = True
        self.assertTrue(state.powerup_used_today)

    def test_powerup_used_today_silenced(self):
        state = DailyPlayerState()
        # silenced=True means this player USED a jinx on someone else
        state.silenced = True
        self.assertTrue(state.powerup_used_today)

    def test_powerup_used_today_stealing(self):
        state = DailyPlayerState()
        # stealing_from set means this player USED a steal on someone else
        state.stealing_from = "p2"
        self.assertTrue(state.powerup_used_today)

    def test_powerup_used_today_passive_effects(self):
        """Test that passive effects (being attacked) do not count as using a powerup."""
        state = DailyPlayerState()

        # Being jinxed by someone else
        state.jinxed_by = "p2"
        self.assertFalse(state.powerup_used_today)

        # Being stolen from
        state.steal_attempt_by = "p2"
        self.assertFalse(state.powerup_used_today)
