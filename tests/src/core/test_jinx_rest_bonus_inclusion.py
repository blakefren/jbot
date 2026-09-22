"""
Test for rest bonus inclusion in jinx transfers.
Regression test to verify rest multiplier is included in jinx calculations.
"""

import unittest
from src.core.state import DailyPlayerState
from src.core.powerup_engine import PowerUpEngine
from src.cfg.main import ConfigReader


class TestJinxRestBonusInclusion(unittest.TestCase):
    """Test that rest multiplier bonus is included in jinx transfers."""

    def setUp(self):
        self.config = ConfigReader()
        self.engine = PowerUpEngine(self.config)
        self.daily_state = {}

    def test_retroactive_jinx_includes_rest_bonus(self):
        """
        Test that when a late jinx is applied to a target who already answered,
        the rest multiplier bonus IS included in the transferred share.

        Scenario:
        - Target answered with 318 points: 265 base + 53 rest bonus
        - Attacker uses late jinx
        - Should transfer 25% of 318 = 79 (includes rest bonus)
        """
        # Setup target state with points and rest bonus
        target_id = "target_123"
        target_state = DailyPlayerState()
        target_state.is_correct = True
        target_state.score_earned = 318  # 265 + 53 rest bonus
        target_state.score_stolen = 0
        target_state.bonuses = {"rest": 53, "streak": 25, "try_1": 20}

        # Setup attacker state
        attacker_id = "attacker_456"
        attacker_state = DailyPlayerState()

        self.daily_state[target_id] = target_state
        self.daily_state[attacker_id] = attacker_state

        # Apply late jinx (retroactive, since target already answered)
        transferred = self.engine.apply_jinx(self.daily_state, attacker_id, target_id)

        # Verify transfer includes rest bonus
        # 25% of 318 = 79.5 ≈ 79
        expected_transfer = 79
        self.assertEqual(transferred, expected_transfer)

        # Verify attacker gained the correct amount
        self.assertEqual(attacker_state.score_earned, expected_transfer)

        # Verify target lost the correct amount
        self.assertEqual(target_state.score_earned, 318 - expected_transfer)

    def test_resolve_jinx_on_correct_includes_rest_bonus(self):
        """
        Test that resolve_jinx_on_correct (forward jinx resolution)
        also includes rest bonus in transfer.
        """
        # Setup target state with points and rest bonus
        target_id = "target_123"
        target_state = DailyPlayerState()
        target_state.score_earned = 318
        target_state.score_stolen = 0
        target_state.bonuses = {"rest": 53, "streak": 25}

        # Setup attacker state with jinx already established
        attacker_id = "attacker_456"
        attacker_state = DailyPlayerState()
        attacker_state.jinx_target = target_id  # Link is established but not resolved

        target_state.jinxed_by = attacker_id

        self.daily_state[target_id] = target_state
        self.daily_state[attacker_id] = attacker_state

        # Resolve jinx when target answers correctly
        transferred = self.engine.resolve_jinx_on_correct(self.daily_state, target_id)

        # Verify transfer includes rest bonus
        # 25% of 318 = 79
        expected_transfer = 79
        self.assertEqual(transferred, expected_transfer)

    def test_jinx_transfers_correct_amount_with_multiple_bonuses(self):
        """
        Test a more complex scenario with multiple bonuses and stolen points.
        Rest bonus is included in the transfer calculation.
        """
        # Target: 500 points total, includes 100 rest bonus, 30 already stolen
        target_id = "target_789"
        target_state = DailyPlayerState()
        target_state.is_correct = True
        target_state.score_earned = 500  # Includes rest bonus
        target_state.score_stolen = 30  # Already lost 30 to another steal
        target_state.bonuses = {"rest": 100, "streak": 50, "try_1": 20}

        attacker_id = "attacker_abc"
        attacker_state = DailyPlayerState()

        self.daily_state[target_id] = target_state
        self.daily_state[attacker_id] = attacker_state

        # Apply late jinx
        transferred = self.engine.apply_jinx(self.daily_state, attacker_id, target_id)

        # 25% of (500 - 30_stolen) = 25% of 470 = 117.5 ≈ 117
        # Rest bonus (100) is included in the 500
        expected_transfer = 117
        self.assertEqual(transferred, expected_transfer)

    def test_jinx_without_rest_bonus(self):
        """
        Test that jinx works correctly for targets without rest bonus.
        This verifies normal case (non-rest) still works as expected.
        """
        # Target: 250 points, no rest bonus
        target_id = "target_def"
        target_state = DailyPlayerState()
        target_state.is_correct = True
        target_state.score_earned = 250
        target_state.score_stolen = 0
        target_state.bonuses = {"streak": 25, "try_1": 20}  # No rest

        attacker_id = "attacker_ghi"
        attacker_state = DailyPlayerState()

        self.daily_state[target_id] = target_state
        self.daily_state[attacker_id] = attacker_state

        # Apply late jinx
        transferred = self.engine.apply_jinx(self.daily_state, attacker_id, target_id)

        # 25% of (250 - 0) = 62.5 ≈ 62
        expected_transfer = 62
        self.assertEqual(transferred, expected_transfer)


if __name__ == "__main__":
    unittest.main()
