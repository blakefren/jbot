# tests/src/core/test_discord.py
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

import sys
import os

# Add the project root to the Python path
project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
sys.path.insert(0, project_root)

from src.core.discord import DiscordBot, MORNING_TIME, REMINDER_TIME, EVENING_TIME


class TestDiscordBotTasks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Create a mock for the bot instance
        self.bot = MagicMock(spec=DiscordBot)
        self.bot.game = MagicMock()
        self.bot.guilds = [MagicMock()]
        self.bot.get_cog = MagicMock()
        self.bot.config = MagicMock()
        self.bot._log_task_error = MagicMock()
        self.bot._send_daily_message_to_all_subscribers = AsyncMock()

        # Mock the RolesCog
        self.roles_cog = MagicMock()
        self.roles_cog.roles_game_mode = MagicMock()
        self.roles_cog.apply_discord_roles = AsyncMock()
        self.bot.get_cog.return_value = self.roles_cog

        # Get coroutines from the tasks
        self.morning_task_coro = DiscordBot.morning_message_task.coro
        self.reminder_task_coro = DiscordBot.reminder_message_task.coro
        self.evening_task_coro = DiscordBot.evening_message_task.coro

    # --- Morning Task Tests ---

    async def test_morning_message_task_success(self):
        """Verify the morning task runs successfully."""
        await self.morning_task_coro(self.bot, silent=False)
        self.bot.game.set_daily_question.assert_called_once()
        self.bot._send_daily_message_to_all_subscribers.assert_awaited_once()
        self.bot._log_task_error.assert_not_called()

    async def test_morning_message_task_silent(self):
        """Verify the morning task does not send messages when silent."""
        await self.morning_task_coro(self.bot, silent=True)
        self.bot.game.set_daily_question.assert_called_once()
        self.bot._send_daily_message_to_all_subscribers.assert_not_awaited()

    async def test_morning_message_task_set_question_fails(self):
        """Verify task handles failure in setting the daily question."""
        self.bot.game.set_daily_question.side_effect = Exception("DB error")
        await self.morning_task_coro(self.bot, silent=False)
        self.bot.game.set_daily_question.assert_called_once()
        self.bot._log_task_error.assert_called_once()
        self.bot._send_daily_message_to_all_subscribers.assert_not_awaited()

    async def test_morning_message_task_send_message_fails(self):
        """Verify task handles failure in sending the message."""
        self.bot._send_daily_message_to_all_subscribers.side_effect = Exception(
            "Discord API error"
        )
        await self.morning_task_coro(self.bot, silent=False)
        self.bot.game.set_daily_question.assert_called_once()
        self.bot._send_daily_message_to_all_subscribers.assert_awaited_once()
        self.bot._log_task_error.assert_called_once()

    # --- Reminder Task Tests ---

    async def test_reminder_message_task_success(self):
        """Verify the reminder task runs successfully."""
        self.bot.game.daily_q = MagicMock()  # Question is set
        await self.reminder_task_coro(self.bot, silent=False)
        self.bot._send_daily_message_to_all_subscribers.assert_awaited_once()
        self.bot._log_task_error.assert_not_called()

    async def test_reminder_message_task_silent(self):
        """Verify the reminder task does not send messages when silent."""
        self.bot.game.daily_q = MagicMock()
        await self.reminder_task_coro(self.bot, silent=True)
        self.bot._send_daily_message_to_all_subscribers.assert_not_awaited()

    async def test_reminder_message_task_no_question(self):
        """Verify the reminder task skips if no question is set."""
        self.bot.game.daily_q = None
        await self.reminder_task_coro(self.bot, silent=False)
        self.bot._send_daily_message_to_all_subscribers.assert_not_awaited()
        self.bot._log_task_error.assert_not_called()

    async def test_reminder_message_task_send_fails(self):
        """Verify the reminder task logs an error if sending fails."""
        self.bot.game.daily_q = MagicMock()
        self.bot._send_daily_message_to_all_subscribers.side_effect = Exception(
            "Network error"
        )
        await self.reminder_task_coro(self.bot, silent=False)
        self.bot._send_daily_message_to_all_subscribers.assert_awaited_once()
        self.bot._log_task_error.assert_called_once()

    # --- Evening Task Tests ---

    async def test_evening_message_task_success(self):
        """Verify the evening task runs all steps successfully."""
        await self.evening_task_coro(self.bot, silent=False)
        self.bot.game.update_scores.assert_called_once()
        self.bot.get_cog.assert_called_with("RolesCog")
        self.roles_cog.roles_game_mode.run.assert_called_once()
        self.roles_cog.apply_discord_roles.assert_awaited_once_with(self.bot.guilds[0])
        self.bot._send_daily_message_to_all_subscribers.assert_awaited_once()
        self.bot._log_task_error.assert_not_called()

    async def test_evening_message_task_update_scores_fails(self):
        """Verify task stops if updating scores fails."""
        self.bot.game.update_scores.side_effect = Exception("Scoring error")
        await self.evening_task_coro(self.bot, silent=False)
        self.bot.game.update_scores.assert_called_once()
        self.bot._log_task_error.assert_called_once()
        # Other steps should not be called
        self.bot.get_cog.assert_not_called()
        self.bot._send_daily_message_to_all_subscribers.assert_not_awaited()

    async def test_evening_message_task_update_roles_fails(self):
        """Verify task continues if updating roles fails."""
        self.roles_cog.roles_game_mode.run.side_effect = Exception("Role DB error")
        await self.evening_task_coro(self.bot, silent=False)
        self.bot.game.update_scores.assert_called_once()
        self.bot.get_cog.assert_called_with("RolesCog")
        self.roles_cog.roles_game_mode.run.assert_called_once()
        self.bot._log_task_error.assert_called_once()
        # Message sending should still happen
        self.bot._send_daily_message_to_all_subscribers.assert_awaited_once()

    async def test_evening_message_task_send_message_fails(self):
        """Verify task logs error if sending the evening message fails."""
        self.bot._send_daily_message_to_all_subscribers.side_effect = Exception(
            "Final message error"
        )
        await self.evening_task_coro(self.bot, silent=False)
        self.bot.game.update_scores.assert_called_once()
        self.bot.get_cog.assert_called_with("RolesCog")
        self.bot._send_daily_message_to_all_subscribers.assert_awaited_once()
        # The final error should be logged
        self.bot._log_task_error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
