import unittest
from unittest.mock import AsyncMock, MagicMock
import discord

from src.cogs.admin import Admin
from src.core.player_manager import PlayerManager
from src.core.game_runner import GameRunner
from db.database import Database


class TestAdminAddAnswer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.morning_message_task = MagicMock()
        self.bot.evening_message_task = MagicMock()
        # Tasks not running -> answer not revealed
        self.bot.morning_message_task.is_running.return_value = False
        self.bot.evening_message_task.is_running.return_value = False

        self.bot.game = MagicMock()

        # Mocks for managers
        self.bot.player_manager = MagicMock(spec=PlayerManager)
        self.bot.data_manager = MagicMock()
        self.bot.data_manager.db = MagicMock(spec=Database)

        self.cog = Admin(self.bot)

        # Mock Context
        self.ctx = MagicMock()
        # Setup author ID for permissions/logging
        self.ctx.author.id = 12345

        # Async methods on context
        self.ctx.send = AsyncMock()
        self.ctx.channel.send = AsyncMock()

        # Interaction context setup
        self.ctx.interaction = MagicMock()
        self.ctx.interaction.response.defer = AsyncMock()
        self.ctx.interaction.followup.send = AsyncMock()

        # Add basic game mock method
        self.bot.game.recalculate_scores_for_new_answer = AsyncMock()

    async def test_add_answer_apply_success(self):
        """Test add_answer with apply=True sends both ephemeral details and public summary."""
        # 1. Mock result from game engine
        mock_result = {
            "status": "success",
            "updated_players": 2,
            "total_refunded": 500,
            "age_warning": None,
            "details": [
                {
                    "name": "Player1",
                    "score_before": 100,
                    "score_after": 300,
                    "diff": 200,
                    "badges": ["BADGE"],
                },
                {
                    "name": "Player2",
                    "score_before": 200,
                    "score_after": 500,
                    "diff": 300,
                    "badges": [],
                },
            ],
        }
        self.bot.game.recalculate_scores_for_new_answer = MagicMock(
            return_value=mock_result
        )

        # 2. Run command
        await self.cog.add_answer.callback(
            self.cog, self.ctx, answer_text="New Answer", apply=True
        )

        # 3. Verify ephemeral deferral
        self.ctx.interaction.response.defer.assert_called_once_with(ephemeral=True)

        # 4. Verify backend call
        self.bot.game.recalculate_scores_for_new_answer.assert_called_once_with(
            "New Answer", "12345", dry_run=False
        )

        # 5. Verify ephemeral details sent to admin
        # Should contain answer text and details
        # The first call to followup.send is the one we care about
        ephemeral_calls = self.ctx.interaction.followup.send.call_args_list
        self.assertTrue(
            len(ephemeral_calls) > 0, "Expected at least one followup message"
        )

        # Get the first call's arguments
        call_args_ephemeral = ephemeral_calls[0][0][0]

        self.assertIn("Added alternative answer", call_args_ephemeral)
        self.assertIn("Player1: 100 -> 300 (+200)", call_args_ephemeral)
        self.assertIn("Player2: 200 -> 500 (+300)", call_args_ephemeral)

        # 6. Verify public message sent to channel
        self.ctx.channel.send.assert_called_once()
        call_args_public = self.ctx.channel.send.call_args[0][0]

        # Public message should contain summary but NOT the actual answer text "New Answer"
        self.assertIn("Score Adjustment:", call_args_public)
        self.assertIn("Player1", call_args_public)
        self.assertIn("Player2", call_args_public)
        # Ensure answer text is NOT leaked
        self.assertNotIn("New Answer", call_args_public)

    async def test_add_answer_dry_run(self):
        """Test add_answer with apply=False (default) sends only ephemeral details."""
        mock_result = {
            "status": "success",
            "updated_players": 1,
            "total_refunded": 100,
            "age_warning": None,
            "details": [
                {
                    "name": "Player1",
                    "score_before": 100,
                    "score_after": 200,
                    "diff": 100,
                    "badges": [],
                }
            ],
        }
        self.bot.game.recalculate_scores_for_new_answer = MagicMock(
            return_value=mock_result
        )

        # Run command with apply=False
        await self.cog.add_answer.callback(
            self.cog, self.ctx, answer_text="New Answer", apply=False
        )

        # Verify call was a dry run
        self.bot.game.recalculate_scores_for_new_answer.assert_called_once_with(
            "New Answer", "12345", dry_run=True
        )

        # Verify message says [DRY RUN]
        call_args = self.ctx.interaction.followup.send.call_args[0][0]
        self.assertIn("[DRY RUN]", call_args)

        # Verify NO public message sent
        self.ctx.channel.send.assert_not_called()

    async def test_add_answer_error(self):
        """Test add_answer handles errors gracefully."""
        mock_result = {"status": "error", "message": "Something went wrong"}
        self.bot.game.recalculate_scores_for_new_answer = MagicMock(
            return_value=mock_result
        )

        await self.cog.add_answer.callback(
            self.cog, self.ctx, answer_text="Fail Answer", apply=True
        )

        self.ctx.interaction.followup.send.assert_called_once()
        args = self.ctx.interaction.followup.send.call_args[0][0]
        self.assertIn("Error: Something went wrong", args)

        self.ctx.channel.send.assert_not_called()
