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
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

from src.cogs.admin import Admin
from src.core.game_runner import GameRunner
from src.core.powerup import PowerUpManager
from src.core.player_manager import PlayerManager
from src.core.data_manager import DataManager
from src.core.state import DailyPlayerState
from data.readers.question import Question
from db.database import Database
from tests.src.core._powerup_helpers import make_config


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


class TestJinxStealAfterAddAnswer(unittest.IsolatedAsyncioTestCase):
    """Exercise answer correction through Admin, SQLite, and live power-ups."""

    async def asyncSetUp(self):
        self.db = Database(":memory:")
        self.data_manager = DataManager(self.db)
        self.player_manager = PlayerManager(self.data_manager)

        for player_id, name, score, streak in (
            ("12345", "Admin", 0, 0),
            ("attacker", "Attacker", 100, 8),
            ("target", "Target", 100, 0),
        ):
            self.data_manager.create_player(player_id, name)
            self.player_manager.update_score(player_id, score)
            self.player_manager.set_streak(player_id, streak)

        self.question = Question(
            question="A test question",
            answer="Original",
            category="Test",
            clue_value=100,
        )
        self.daily_question_id = self.data_manager.log_daily_question(self.question)
        self.question_db_id = self.db.execute_query(
            "SELECT question_id FROM daily_questions WHERE id = ?",
            (self.daily_question_id,),
        )[0]["question_id"]
        self.data_manager.log_player_guess(
            "target", "Target", self.daily_question_id, "Accepted spelling", False
        )

        self.config = make_config(retro_steal_cost=4)
        self.config.get_bool.return_value = False
        with patch("src.core.game_runner.ConfigReader", return_value=self.config):
            self.game = GameRunner(
                MagicMock(), self.data_manager, player_manager=self.player_manager
            )
        self.game.daily_q = self.question
        self.game.daily_question_id = self.daily_question_id
        self.game.question_db_id = self.question_db_id
        self.game.restore_game_state()

        self.bot = MagicMock()
        self.bot.game = self.game
        self.bot.morning_message_task.is_running.return_value = False
        self.bot.evening_message_task.is_running.return_value = False
        self.cog = Admin(self.bot)

        self.ctx = MagicMock()
        self.ctx.author.id = 12345
        self.ctx.interaction.response.defer = AsyncMock()
        self.ctx.interaction.followup.send = AsyncMock()
        self.ctx.channel.send = AsyncMock()

    async def asyncTearDown(self):
        self.db.close()

    async def _apply_answer_correction(self):
        powerup_manager = self.game.managers["powerup"]
        self.assertFalse(powerup_manager.daily_state["target"].is_correct)

        await self.cog.add_answer.callback(
            self.cog, self.ctx, answer_text="Accepted spelling", apply=True
        )

        corrected_guess = self.data_manager.get_guesses_for_daily_question(
            self.daily_question_id
        )[0]
        self.assertTrue(corrected_guess["is_correct"])
        self.assertTrue(powerup_manager.daily_state["target"].is_correct)
        return powerup_manager

    async def test_jinx_after_correction_is_retroactive(self):
        powerup_manager = await self._apply_answer_correction()
        target_score = self.player_manager.get_player("target").score
        attacker_score = self.player_manager.get_player("attacker").score

        message = powerup_manager.jinx("attacker", "target", self.daily_question_id)

        self.assertIn("already answered", message)
        self.assertLess(self.player_manager.get_player("target").score, target_score)
        self.assertGreater(
            self.player_manager.get_player("attacker").score, attacker_score
        )

    async def test_steal_after_correction_is_retroactive(self):
        powerup_manager = await self._apply_answer_correction()
        target_score = self.player_manager.get_player("target").score
        attacker_score = self.player_manager.get_player("attacker").score

        message = powerup_manager.steal("attacker", "target", self.daily_question_id)

        self.assertIn("already answered", message)
        self.assertLess(self.player_manager.get_player("target").score, target_score)
        self.assertGreater(
            self.player_manager.get_player("attacker").score, attacker_score
        )

    async def test_answer_correction_failure_rolls_back_all_database_changes(self):
        target_before = self.player_manager.get_player("target")
        original_log_score_adjustment = self.data_manager.log_score_adjustment

        def log_then_fail(*args, **kwargs):
            original_log_score_adjustment(*args, **kwargs)
            raise sqlite3.OperationalError("injected correction failure")

        with patch.object(
            self.data_manager,
            "log_score_adjustment",
            side_effect=log_then_fail,
        ):
            with self.assertRaisesRegex(
                sqlite3.OperationalError, "injected correction failure"
            ):
                self.game.recalculate_scores_for_new_answer(
                    "Accepted spelling", "admin"
                )

        self.assertEqual(
            self.data_manager.get_alternative_answers(self.question_db_id), []
        )
        guesses = self.data_manager.get_guesses_for_daily_question(
            self.daily_question_id
        )
        self.assertFalse(guesses[0]["is_correct"])
        target_after = self.player_manager.get_player("target")
        self.assertEqual(target_after.score, target_before.score)
        self.assertEqual(target_after.answer_streak, target_before.answer_streak)
        self.assertEqual(
            self.db.execute_query(
                "SELECT * FROM score_adjustments WHERE player_id = ?", ("target",)
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
