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
        """apply=True: single public message with @mentions; ephemeral is just 'Done.'"""
        mock_result = {
            "status": "success",
            "updated_players": 2,
            "total_refunded": 500,
            "age_warning": None,
            "rest_cleared_players": [],
            "details": [
                {
                    "user_id": "111",
                    "name": "Player1",
                    "score_before": 100,
                    "score_after": 300,
                    "diff": 200,
                    "badges": ["BADGE"],
                },
                {
                    "user_id": "222",
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

        await self.cog.add_answer.callback(
            self.cog, self.ctx, answer_text="New Answer", apply=True
        )

        self.ctx.interaction.response.defer.assert_called_once_with(ephemeral=True)
        self.bot.game.recalculate_scores_for_new_answer.assert_called_once_with(
            "New Answer", "12345", dry_run=False
        )

        # Ephemeral reply is just a silent "Done."
        ephemeral_text = self.ctx.interaction.followup.send.call_args[0][0]
        self.assertEqual(ephemeral_text, "Done.")

        # Public message uses @mentions and contains the summary
        self.ctx.channel.send.assert_called_once()
        public_text = self.ctx.channel.send.call_args[0][0]
        self.assertIn("Score Adjustment:", public_text)
        self.assertIn("<@111>", public_text)
        self.assertIn("<@222>", public_text)
        # Answer not revealed — answer text must NOT appear
        self.assertNotIn("New Answer", public_text)

    async def test_add_answer_dry_run(self):
        """apply=False: single ephemeral message with [DRY RUN], plain names, no public."""
        mock_result = {
            "status": "success",
            "updated_players": 1,
            "total_refunded": 100,
            "age_warning": None,
            "rest_cleared_players": [],
            "details": [
                {
                    "user_id": "111",
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

        await self.cog.add_answer.callback(
            self.cog, self.ctx, answer_text="New Answer", apply=False
        )

        self.bot.game.recalculate_scores_for_new_answer.assert_called_once_with(
            "New Answer", "12345", dry_run=True
        )

        ephemeral_text = self.ctx.interaction.followup.send.call_args[0][0]
        self.assertIn("[DRY RUN]", ephemeral_text)
        # Plain name used — no @mention
        self.assertIn("Player1", ephemeral_text)
        self.assertNotIn("<@111>", ephemeral_text)

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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_result(self, **overrides):
        """Return a minimal success result dict, with optional field overrides."""
        base = {
            "status": "success",
            "updated_players": 1,
            "total_refunded": 100,
            "age_warning": None,
            "rest_cleared_players": [],
            "details": [
                {
                    "user_id": "111",
                    "name": "Player1",
                    "score_before": 100,
                    "score_after": 200,
                    "diff": 100,
                    "badges": [],
                }
            ],
        }
        base.update(overrides)
        return base

    def _set_revealed(self):
        """Configure task mocks so is_revealed=True."""
        from datetime import datetime, timedelta

        self.bot.morning_message_task.is_running.return_value = True
        self.bot.evening_message_task.is_running.return_value = True
        now = datetime.now()
        self.bot.morning_message_task.next_iteration = now + timedelta(hours=1)
        self.bot.evening_message_task.next_iteration = now + timedelta(hours=12)

    # ------------------------------------------------------------------
    # Answer visibility
    # ------------------------------------------------------------------

    async def test_apply_not_revealed_answer_hidden_from_public(self):
        """apply=True, not revealed: answer text must not appear in the public message."""
        self.bot.game.recalculate_scores_for_new_answer = MagicMock(
            return_value=self._make_result()
        )
        await self.cog.add_answer.callback(
            self.cog, self.ctx, answer_text="Secret", apply=True
        )
        public_text = self.ctx.channel.send.call_args[0][0]
        self.assertNotIn("Secret", public_text)

    async def test_apply_revealed_shows_spoiler_in_public(self):
        """apply=True, after reveal: public message shows answer under spoiler tags."""
        self._set_revealed()
        self.bot.game.recalculate_scores_for_new_answer = MagicMock(
            return_value=self._make_result()
        )
        await self.cog.add_answer.callback(
            self.cog, self.ctx, answer_text="SecretAnswer", apply=True
        )
        public_text = self.ctx.channel.send.call_args[0][0]
        self.assertIn("||SecretAnswer||", public_text)

    async def test_dry_run_not_revealed_answer_hidden_from_ephemeral(self):
        """apply=False, not revealed: answer text must not appear in ephemeral message."""
        self.bot.game.recalculate_scores_for_new_answer = MagicMock(
            return_value=self._make_result()
        )
        await self.cog.add_answer.callback(
            self.cog, self.ctx, answer_text="Secret", apply=False
        )
        ephemeral_text = self.ctx.interaction.followup.send.call_args[0][0]
        self.assertNotIn("Secret", ephemeral_text)

    async def test_dry_run_revealed_shows_answer_in_ephemeral(self):
        """apply=False, after reveal: ephemeral shows answer (with spoiler) so admin sees it."""
        self._set_revealed()
        self.bot.game.recalculate_scores_for_new_answer = MagicMock(
            return_value=self._make_result()
        )
        await self.cog.add_answer.callback(
            self.cog, self.ctx, answer_text="SecretAnswer", apply=False
        )
        ephemeral_text = self.ctx.interaction.followup.send.call_args[0][0]
        self.assertIn("||SecretAnswer||", ephemeral_text)

    # ------------------------------------------------------------------
    # Player tagging
    # ------------------------------------------------------------------

    async def test_apply_public_uses_mentions_not_plain_names(self):
        """apply=True: public message uses <@id> mentions, not bare player names."""
        self.bot.game.recalculate_scores_for_new_answer = MagicMock(
            return_value=self._make_result()
        )
        await self.cog.add_answer.callback(
            self.cog, self.ctx, answer_text="Ans", apply=True
        )
        public_text = self.ctx.channel.send.call_args[0][0]
        self.assertIn("<@111>", public_text)

    async def test_dry_run_ephemeral_uses_plain_names_not_mentions(self):
        """apply=False: ephemeral must not contain @mentions."""
        self.bot.game.recalculate_scores_for_new_answer = MagicMock(
            return_value=self._make_result()
        )
        await self.cog.add_answer.callback(
            self.cog, self.ctx, answer_text="Ans", apply=False
        )
        ephemeral_text = self.ctx.interaction.followup.send.call_args[0][0]
        self.assertNotIn("<@", ephemeral_text)

    # ------------------------------------------------------------------
    # Rest-cleared players
    # ------------------------------------------------------------------

    async def test_apply_rest_cleared_mentioned_in_public(self):
        """apply=True: resting players whose guess matched are @mentioned with rest note."""
        result = self._make_result(
            rest_cleared_players=[{"user_id": "999", "name": "Sleepy"}]
        )
        self.bot.game.recalculate_scores_for_new_answer = MagicMock(return_value=result)
        await self.cog.add_answer.callback(
            self.cog, self.ctx, answer_text="Ans", apply=True
        )
        public_text = self.ctx.channel.send.call_args[0][0]
        self.assertIn("<@999>", public_text)
        self.assertIn("Rest revoked", public_text)

    async def test_dry_run_rest_cleared_shows_name_in_ephemeral(self):
        """apply=False: resting players listed by name (no @mention) in dry-run ephemeral."""
        result = self._make_result(
            rest_cleared_players=[{"user_id": "999", "name": "Sleepy"}]
        )
        self.bot.game.recalculate_scores_for_new_answer = MagicMock(return_value=result)
        await self.cog.add_answer.callback(
            self.cog, self.ctx, answer_text="Ans", apply=False
        )
        ephemeral_text = self.ctx.interaction.followup.send.call_args[0][0]
        self.assertIn("Sleepy", ephemeral_text)
        self.assertIn("Rest revoked", ephemeral_text)
        self.assertNotIn("<@999>", ephemeral_text)
