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

    async def test_status_answer_reveal(self):
        """Test status when it's time for answer reveal (evening < morning)."""
        self.bot.morning_message_task.is_running.return_value = True
        self.bot.evening_message_task.is_running.return_value = True

        # Evening is sooner than morning
        self.bot.morning_message_task.next_iteration = datetime(
            2025, 1, 2, 8, 0, tzinfo=timezone.utc
        )
        self.bot.evening_message_task.next_iteration = datetime(
            2025, 1, 1, 20, 0, tzinfo=timezone.utc
        )

        # Ensure no active question so we don't trigger the question display logic
        # which would cause string concatenation with a Mock if not handled
        self.bot.game.daily_q = None

        await self.cog.status.callback(self.cog, self.ctx)

        self.bot.send_message.assert_awaited_once()
        args, kwargs = self.bot.send_message.await_args
        self.assertIn("answer reveal", args[0])

    async def test_status_with_active_question(self):
        """Test status showing the active question."""
        self.bot.morning_message_task.is_running.return_value = True
        self.bot.evening_message_task.is_running.return_value = True

        # Morning < Evening (Next question phase, but we want to show today's question if it exists)
        # Wait, the logic in game.py says:
        # if self.bot.game.daily_q and morning_time_next > evening_time_next:
        # This implies we show the question if we are waiting for the answer reveal (evening).
        # So morning > evening means evening comes first.

        self.bot.morning_message_task.next_iteration = datetime(
            2025, 1, 2, 8, 0, tzinfo=timezone.utc
        )
        self.bot.evening_message_task.next_iteration = datetime(
            2025, 1, 1, 20, 0, tzinfo=timezone.utc
        )

        self.bot.game.daily_q = MagicMock()
        self.bot.game.format_question.return_value = "Formatted Question"

        await self.cog.status.callback(self.cog, self.ctx)

        self.bot.send_message.assert_awaited_once()
        args, kwargs = self.bot.send_message.await_args
        self.assertIn("Today's Question:", args[0])
        self.assertIn("Formatted Question", args[0])

    async def test_status_with_player_stats(self):
        """Test status showing player stats."""
        self.bot.morning_message_task.is_running.return_value = True
        self.bot.evening_message_task.is_running.return_value = True
        self.bot.morning_message_task.next_iteration = datetime(
            2025, 1, 1, 8, 0, tzinfo=timezone.utc
        )
        self.bot.evening_message_task.next_iteration = datetime(
            2025, 1, 1, 20, 0, tzinfo=timezone.utc
        )

        mock_player = MagicMock()
        mock_player.score = 100
        mock_player.answer_streak = 5
        self.bot.player_manager.get_player.return_value = mock_player

        await self.cog.status.callback(self.cog, self.ctx)

        self.bot.send_message.assert_awaited_once()
        args, kwargs = self.bot.send_message.await_args
        self.assertIn("**Your Score:** 100", args[0])
        self.assertIn("**Streak:** 5", args[0])

    async def test_status_player_not_found(self):
        """Test status when player is not found."""
        self.bot.morning_message_task.is_running.return_value = True
        self.bot.evening_message_task.is_running.return_value = True
        self.bot.morning_message_task.next_iteration = datetime(
            2025, 1, 1, 8, 0, tzinfo=timezone.utc
        )
        self.bot.evening_message_task.next_iteration = datetime(
            2025, 1, 1, 20, 0, tzinfo=timezone.utc
        )

        self.bot.player_manager.get_player.return_value = None

        await self.cog.status.callback(self.cog, self.ctx)

        self.bot.send_message.assert_awaited_once()
        args, kwargs = self.bot.send_message.await_args
        self.assertNotIn("**Your Score:**", args[0])

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

    async def test_rules_no_features(self):
        """Test rules command with no features enabled."""
        self.bot.game.features = {"fight": False}

        await self.cog.rules.callback(self.cog, self.ctx)

        self.bot.send_message.assert_awaited_once()
        args, kwargs = self.bot.send_message.await_args
        self.assertIn("Standard trivia rules apply", args[0])

    async def test_rules_all_features(self):
        """Test rules command with all features enabled."""
        self.bot.game.features = {"fight": True}

        await self.cog.rules.callback(self.cog, self.ctx)

        self.bot.send_message.assert_awaited_once()
        args, kwargs = self.bot.send_message.await_args
        self.assertIn("Fight Track", args[0])
        # Power-up and Coop tracks are no longer toggleable features in rules
        # self.assertIn("Power-up Track", args[0])
        # self.assertIn("Coop Track", args[0])

    async def test_game_group(self):
        """Test the game group command sends help."""
        self.ctx.invoked_subcommand = None
        await self.cog.game.callback(self.cog, self.ctx)
        self.ctx.send_help.assert_awaited_once_with(self.ctx.command)

    async def test_setup(self):
        """Test the setup function."""
        from src.cogs.game import setup

        mock_bot = MagicMock()
        mock_bot.add_cog = AsyncMock()
        await setup(mock_bot)
        mock_bot.add_cog.assert_called_once()
