"""
Test retaliation blocking for power-ups.

When one player attacks another (jinx or steal), the target cannot
retaliate (attack back) on the same day.
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, date
from src.core.powerup import PowerUpManager, PowerUpError
from src.core.state import DailyPlayerState
from src.core.player import Player
from src.cfg.main import ConfigReader


class TestRetaliationBlocking(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        self.player_manager = MagicMock()
        self.data_manager = MagicMock()
        self.config = MagicMock(spec=ConfigReader)

        # Configure config mocks with all required values
        self.config.get.side_effect = lambda key, default=None: {
            "JBOT_EMOJI_JINXED": "🥶",
            "JBOT_EMOJI_SILENCED": "🤐",
            "JBOT_EMOJI_STOLEN_FROM": "💸",
            "JBOT_EMOJI_STEALING": "💰",
            "JBOT_EMOJI_REST": "😴",
            "JBOT_EMOJI_REST_WAKEUP": "⏰",
            "JBOT_EMOJI_STREAK": "🔥",
            "JBOT_EMOJI_FIRST_TRY": "⭐",
            "JBOT_EMOJI_BEFORE_HINT": "💡",
            "JBOT_EMOJI_FASTEST": "⚡",
            "JBOT_EMOJI_FASTEST_CSV": "🥇,🥈,🥉",
            "JBOT_REST_BONUS_PER_DAY": "0.2",
            "JBOT_STEAL_STREAK_COST": "3",
            "JBOT_RETRO_STEAL_STREAK_COST": "5",
            "JBOT_JINX_SHARE_RATIO": "0.25",
            "JBOT_JINX_WRONG_GUESS_PENALTY": "5",
            "JBOT_BONUS_TRY_CSV": "20,10,5",
            "JBOT_BONUS_FASTEST_CSV": "15,10,5",
            "JBOT_BONUS_BEFORE_HINT": "10",
            "JBOT_BONUS_STREAK_PER_DAY": "5",
            "JBOT_BONUS_STREAK_CAP": "100",
            "JBOT_CROWD_WISDOM_DECAY_K": "1.15",
        }.get(key, default)

        self.config.get_bool.side_effect = lambda key, default=False: default

        # Create PowerUpManager
        self.manager = PowerUpManager(
            self.player_manager, self.data_manager, self.config
        )

        # Mock player data
        self.player_manager.get_player.side_effect = lambda pid: Player(
            id=pid,
            name=f"Player{pid}",
            answer_streak=10,
        )

        # Mock data manager
        self.data_manager.get_pending_powerup.return_value = None
        self.data_manager.get_pending_powerup_for_target.return_value = None
        self.data_manager.get_last_correct_guess_date.return_value = None
        self.data_manager.get_today.return_value = date.today()

    def test_jinx_blocks_retaliation(self):
        """Test that after being jinxed, a player cannot jinx back."""
        attacker_id = "attacker"
        target_id = "target"
        question_id = 1

        # Attacker jinxes target
        self.manager.jinx(attacker_id, target_id, question_id)

        # Verify target's attacked_by now contains attacker
        target_state = self.manager._get_daily_state(target_id)
        self.assertIn(attacker_id, target_state.attacked_by)

        # Target tries to retaliate (jinx back) - should be blocked
        with self.assertRaises(PowerUpError) as context:
            self.manager.jinx(target_id, attacker_id, question_id)

        self.assertIn("retaliat", str(context.exception).lower())

    def test_steal_blocks_retaliation(self):
        """Test that after being stolen from, a player cannot steal back."""
        thief_id = "thief"
        target_id = "target"
        question_id = 1

        # Thief steals from target
        self.manager.steal(thief_id, target_id, question_id)

        # Verify target's attacked_by now contains thief
        target_state = self.manager._get_daily_state(target_id)
        self.assertIn(thief_id, target_state.attacked_by)

        # Target tries to retaliate (steal back) - should be blocked
        with self.assertRaises(PowerUpError) as context:
            self.manager.steal(target_id, thief_id, question_id)

        self.assertIn("retaliat", str(context.exception).lower())

    def test_jinx_then_steal_blocks_retaliation(self):
        """Test that after being jinxed, a player cannot steal."""
        attacker_id = "attacker"
        target_id = "target"
        question_id = 1

        # Attacker jinxes target
        self.manager.jinx(attacker_id, target_id, question_id)

        # Target tries to steal back - should be blocked even though it's a different attack type
        with self.assertRaises(PowerUpError) as context:
            self.manager.steal(target_id, attacker_id, question_id)

        self.assertIn("retaliat", str(context.exception).lower())

    def test_steal_then_jinx_blocks_retaliation(self):
        """Test that after being stolen from, a player cannot jinx."""
        attacker_id = "attacker"
        target_id = "target"
        question_id = 1

        # Attacker steals from target
        self.manager.steal(attacker_id, target_id, question_id)

        # Target tries to jinx back - should be blocked even though it's a different attack type
        with self.assertRaises(PowerUpError) as context:
            self.manager.jinx(target_id, attacker_id, question_id)

        self.assertIn("retaliat", str(context.exception).lower())

    def test_overnight_jinx_blocks_retaliation(self):
        """Test that after being targeted for overnight jinx, player cannot retaliate."""
        attacker_id = "attacker"
        target_id = "target"

        # Mock overnight state
        self.data_manager.get_pending_powerup.return_value = None

        # Attacker queues overnight jinx for target
        self.manager.jinx(attacker_id, target_id, question_id=None)

        # Verify target's attacked_by now contains attacker
        target_state = self.manager._get_daily_state(target_id)
        self.assertIn(attacker_id, target_state.attacked_by)

        # Target tries to retaliate overnight - should be blocked
        with self.assertRaises(PowerUpError) as context:
            self.manager.jinx(target_id, attacker_id, question_id=None)

        self.assertIn("retaliat", str(context.exception).lower())

    def test_overnight_steal_blocks_retaliation(self):
        """Test that after being targeted for overnight steal, player cannot retaliate."""
        thief_id = "thief"
        target_id = "target"

        # Mock overnight state
        self.data_manager.get_pending_powerup.return_value = None

        # Thief queues overnight steal for target
        self.manager.steal(thief_id, target_id, question_id=None)

        # Verify target's attacked_by now contains thief
        target_state = self.manager._get_daily_state(target_id)
        self.assertIn(thief_id, target_state.attacked_by)

        # Target tries to retaliate overnight - should be blocked
        with self.assertRaises(PowerUpError) as context:
            self.manager.steal(target_id, thief_id, question_id=None)

        self.assertIn("retaliat", str(context.exception).lower())

    def test_non_retaliatory_attack_allowed(self):
        """Test that a non-retaliatory attacks are allowed."""
        attacker_id = "attacker"
        target_id = "target"
        third_player = "third"
        fourth_player = "fourth"
        question_id = 1

        # Attacker jinxes target
        self.manager.jinx(attacker_id, target_id, question_id)

        # Target jinxes third player (not retaliation)
        # Should not raise an error
        self.manager.jinx(target_id, third_player, question_id)

        # Third player can still attack fourth player (not retaliation)
        # Should not raise an error
        self.manager.jinx(third_player, fourth_player, question_id)

        # Fourth player can attack the first player (not retaliation)
        # Should not raise an error
        self.manager.jinx(fourth_player, attacker_id, question_id)

        # Verify third player is in fourth player's attacked_by set
        fourth_state = self.manager._get_daily_state(fourth_player)
        self.assertIn(third_player, fourth_state.attacked_by)


if __name__ == "__main__":
    unittest.main()
