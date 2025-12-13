import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from src.cogs.game import Game
from src.core.discord import DiscordBot


class TestGameCog(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock(spec=DiscordBot)
        self.bot.game = MagicMock()
        self.bot.player_manager = MagicMock()
        self.bot.morning_message_task = MagicMock()
        self.bot.evening_message_task = MagicMock()
        self.bot.send_message = AsyncMock()

        self.cog = Game(self.bot)
        self.ctx = AsyncMock()
        self.ctx.interaction = MagicMock()

    async def test_status_tasks_not_running(self):
        self.bot.morning_message_task.is_running.return_value = False
        await self.cog.status.callback(self.cog, self.ctx)
        self.bot.send_message.assert_awaited_once()
        args, kwargs = self.bot.send_message.await_args
        self.assertIn("Tasks are not running", args[0])

    async def test_status_next_question(self):
        self.bot.morning_message_task.is_running.return_value = True
        self.bot.evening_message_task.is_running.return_value = True

        # Morning is sooner than evening (next day vs today)
        self.bot.morning_message_task.next_iteration = datetime(
            2025, 1, 1, 8, 0, tzinfo=timezone.utc
        )
        self.bot.evening_message_task.next_iteration = datetime(
            2025, 1, 1, 20, 0, tzinfo=timezone.utc
        )

        # Current time is before morning
        # Actually the logic compares next_iteration.
        # If morning < evening, it means morning comes first.

        await self.cog.status.callback(self.cog, self.ctx)

        self.bot.send_message.assert_awaited_once()
        args, kwargs = self.bot.send_message.await_args
        self.assertIn("next question", args[0])

    async def test_leaderboard(self):
        self.bot.game.get_scores_leaderboard.return_value = "Leaderboard"
        await self.cog.leaderboard.callback(self.cog, self.ctx)
        self.bot.send_message.assert_awaited_once_with(
            "Leaderboard", interaction=self.ctx.interaction
        )

    async def test_profile(self):
        self.ctx.author.id = 123
        self.ctx.author.display_name = "Test"
        self.bot.game.get_player_history.return_value = "History"

        await self.cog.profile.callback(self.cog, self.ctx)

        self.bot.game.get_player_history.assert_called_once_with(123, "Test")
        self.bot.send_message.assert_awaited_once_with(
            "History", interaction=self.ctx.interaction, ephemeral=True
        )

    async def test_rules(self):
        self.bot.game.features = {"fight": True, "powerup": False, "coop": False}

        await self.cog.rules.callback(self.cog, self.ctx)

        self.bot.send_message.assert_awaited_once()
        args, kwargs = self.bot.send_message.await_args
        self.assertIn("Fight Track", args[0])
        self.assertNotIn("Power-up Track", args[0])
