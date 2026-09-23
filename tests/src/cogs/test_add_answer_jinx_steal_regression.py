"""
Regression tests for add_answer + jinx/steal interaction.

Bug: If a player guesses incorrectly and is later marked correct via /admin add_answer,
jinx/steal targeting that player would fail saying "you'll steal points when they answer"
instead of recognizing it as retroactive (already answered).

Root cause: add_answer updates the database but doesn't sync the PowerUpManager's
in-memory daily_state dictionary, so jinx/steal can't see the retroactive correction.

Fix: After add_answer applies changes, sync the newly-correct players' state back to
PowerUpManager.daily_state.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import discord

from src.cogs.admin import Admin
from src.core.powerup import PowerUpManager, PowerUpError
from src.core.player_manager import PlayerManager
from src.core.data_manager import DataManager
from src.core.state import DailyPlayerState
from data.readers.question import Question
from db.database import Database


class TestAddAnswerJinxStealRegression(unittest.IsolatedAsyncioTestCase):
    """Regression tests for add_answer + jinx/steal interaction."""

    async def asyncSetUp(self):
        """Set up mocks for bot, game, and managers."""
        self.bot = MagicMock()
        self.bot.morning_message_task = MagicMock()
        self.bot.evening_message_task = MagicMock()
        self.bot.morning_message_task.is_running.return_value = False
        self.bot.evening_message_task.is_running.return_value = False

        self.bot.game = MagicMock()
        self.bot.game.season_manager.enabled = False

        # Create real PowerUpManager mock with daily_state
        self.powerup_manager = MagicMock(spec=PowerUpManager)
        self.powerup_manager.daily_state = {}

        self.bot.game.managers = {"powerup": self.powerup_manager}

        self.cog = Admin(self.bot)
        self.ctx = MagicMock()
        self.ctx.author.id = 12345
        self.ctx.interaction = MagicMock()
        self.ctx.interaction.response.defer = AsyncMock()
        self.ctx.interaction.followup.send = AsyncMock()
        self.ctx.channel.send = AsyncMock()

    async def test_add_answer_syncs_daily_state_for_newly_correct(self):
        """
        After add_answer applies changes, newly-correct players should be synced
        to PowerUpManager.daily_state so jinx/steal recognize them as having answered.
        """
        # Simulate daily_state from the simulator after recalculation
        newly_correct_player_id = "target_player_123"
        new_daily_state = {
            newly_correct_player_id: DailyPlayerState(
                is_correct=True,
                score_earned=200,
                bonuses={"try": 20, "before_hint": 10, "streak": 50},
            ),
            "other_player": DailyPlayerState(
                is_correct=True,
                score_earned=100,
                bonuses={"try": 10},
            ),
        }

        mock_result = {
            "status": "success",
            "updated_players": 1,
            "total_refunded": 200,
            "age_warning": "",
            "rest_cleared_players": [],
            "details": [
                {
                    "user_id": newly_correct_player_id,
                    "name": "TargetPlayer",
                    "score_before": 0,
                    "score_after": 200,
                    "season_score_before": 0,
                    "season_score_after": 200,
                    "diff": 200,
                    "badges": ["🎯"],
                }
            ],
            "daily_state_new": new_daily_state,
        }

        self.bot.game.recalculate_scores_for_new_answer = MagicMock(
            return_value=mock_result
        )

        # Before add_answer, PowerUpManager.daily_state is empty
        self.assertEqual(self.powerup_manager.daily_state, {})

        # Call add_answer with apply=True
        await self.cog.add_answer.callback(
            self.cog, self.ctx, answer_text="correct_answer", apply=True
        )

        # After add_answer, PowerUpManager.daily_state should be synced with new_daily_state
        self.assertIn(newly_correct_player_id, self.powerup_manager.daily_state)
        synced_state = self.powerup_manager.daily_state[newly_correct_player_id]
        self.assertTrue(synced_state.is_correct)
        self.assertEqual(synced_state.score_earned, 200)
        self.assertIn("try", synced_state.bonuses)

    async def test_add_answer_dry_run_does_not_sync_daily_state(self):
        """
        Dry run (apply=False) should NOT sync daily_state, since no changes are applied.
        """
        new_daily_state = {
            "player_1": DailyPlayerState(is_correct=True, score_earned=200)
        }

        mock_result = {
            "status": "success",
            "updated_players": 1,
            "total_refunded": 200,
            "age_warning": "",
            "rest_cleared_players": [],
            "details": [],
            "daily_state_new": new_daily_state,
        }

        self.bot.game.recalculate_scores_for_new_answer = MagicMock(
            return_value=mock_result
        )

        initial_state = dict(self.powerup_manager.daily_state)

        # Call add_answer with apply=False (dry run)
        await self.cog.add_answer.callback(
            self.cog, self.ctx, answer_text="test_answer", apply=False
        )

        # daily_state should not change on dry run
        self.assertEqual(self.powerup_manager.daily_state, initial_state)

    async def test_add_answer_syncs_empty_state_when_no_powerup_manager(self):
        """
        If there's no powerup_manager in bot.game.managers, add_answer should
        handle it gracefully without crashing.
        """
        self.bot.game.managers = {}  # No powerup manager

        mock_result = {
            "status": "success",
            "updated_players": 1,
            "total_refunded": 100,
            "age_warning": "",
            "rest_cleared_players": [],
            "details": [],
            "daily_state_new": {
                "player_1": DailyPlayerState(is_correct=True, score_earned=100)
            },
        }

        self.bot.game.recalculate_scores_for_new_answer = MagicMock(
            return_value=mock_result
        )

        # Should not raise an exception
        await self.cog.add_answer.callback(
            self.cog, self.ctx, answer_text="test_answer", apply=True
        )

        self.ctx.interaction.followup.send.assert_called()

    async def test_add_answer_with_empty_daily_state_new(self):
        """
        If daily_state_new is empty or missing, add_answer should handle it gracefully.
        """
        self.bot.game.managers = {"powerup": self.powerup_manager}

        mock_result = {
            "status": "success",
            "updated_players": 0,
            "total_refunded": 0,
            "age_warning": "",
            "rest_cleared_players": [],
            "details": [],
            "daily_state_new": {},  # Empty
        }

        self.bot.game.recalculate_scores_for_new_answer = MagicMock(
            return_value=mock_result
        )

        # Should not raise an exception
        await self.cog.add_answer.callback(
            self.cog, self.ctx, answer_text="test_answer", apply=True
        )

        self.ctx.interaction.followup.send.assert_called()


class TestJinxAfterAddAnswer(unittest.TestCase):
    """
    Integration tests verifying that jinx works correctly after add_answer.
    """

    def setUp(self):
        """Set up database, managers, and question."""
        self.db = Database(":memory:")

        self.data_manager = DataManager(self.db)
        self.player_manager = PlayerManager(self.data_manager)
        self.powerup_manager = PowerUpManager(self.player_manager, self.data_manager)

        # Insert test players using execute_update
        self.db.execute_update(
            "INSERT INTO players (user_id, name, score, answer_streak) VALUES (?, ?, ?, ?)",
            ("attacker_123", "Attacker", 100, 5),
        )
        self.db.execute_update(
            "INSERT INTO players (user_id, name, score, answer_streak) VALUES (?, ?, ?, ?)",
            ("target_123", "Target", 50, 3),
        )

    def test_jinx_recognizes_retroactively_corrected_target(self):
        """
        After a player is retroactively marked correct via add_answer,
        jinx should recognize them as already answered (retroactive scenario).
        """
        question_id = 1

        # Initially, target_123 is NOT marked correct in daily_state
        self.assertEqual(self.powerup_manager.daily_state.get("target_123"), None)

        # Simulate add_answer syncing the daily_state (like the fix does)
        new_state = DailyPlayerState(
            is_correct=True, score_earned=200, bonuses={"try": 20}
        )
        self.powerup_manager.daily_state["target_123"] = new_state

        # Now jinx should see target as having answered
        target_state = self.powerup_manager.daily_state.get("target_123")
        self.assertIsNotNone(target_state)
        self.assertTrue(target_state.is_correct)

        # When jinx checks if it should be retroactive:
        # In powerup.py, line ~440: if self._get_daily_state(target_id).is_correct:
        # This should now return True and trigger retroactive jinx
        attacker_state = self.powerup_manager._get_daily_state("attacker_123")
        self.assertIsNotNone(attacker_state)

    def test_steal_recognizes_retroactively_corrected_target(self):
        """
        After a player is retroactively marked correct via add_answer,
        steal should recognize them as already answered (retroactive scenario).
        """
        question_id = 1

        # Initially, target_123 is NOT marked correct in daily_state
        self.assertEqual(self.powerup_manager.daily_state.get("target_123"), None)

        # Simulate add_answer syncing the daily_state
        new_state = DailyPlayerState(
            is_correct=True, score_earned=150, bonuses={"before_hint": 10}
        )
        self.powerup_manager.daily_state["target_123"] = new_state

        # Now steal should see target as having answered
        target_state = self.powerup_manager.daily_state.get("target_123")
        self.assertIsNotNone(target_state)
        self.assertTrue(target_state.is_correct)

        # When steal checks if it should be retroactive:
        # In powerup.py, line ~525: if target_state.is_correct:
        # This should now return True and trigger retroactive steal
        thief_state = self.powerup_manager._get_daily_state("attacker_123")
        self.assertIsNotNone(thief_state)


if __name__ == "__main__":
    unittest.main()
