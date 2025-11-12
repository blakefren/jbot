# tests/src/core/test_discord.py
import unittest
from unittest.mock import MagicMock, AsyncMock

import sys
import os

# Add the project root to the Python path
project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
sys.path.insert(0, project_root)

from src.core.discord import DiscordBot


class TestDiscordBotTasks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock(spec=DiscordBot)
        self.bot.game = MagicMock()
        self.bot.guilds = [MagicMock()]
        self.bot.get_cog = MagicMock()

        # Mock the RolesCog
        self.roles_cog = MagicMock()
        self.roles_cog.roles_game_mode = MagicMock()
        self.roles_cog.apply_discord_roles = AsyncMock()

        # Configure the bot's get_cog method to return our mock
        self.bot.get_cog.return_value = self.roles_cog

        # The task itself is a class attribute. We can get its coroutine.
        self.evening_task_coro = DiscordBot.evening_message_task.coro

    async def test_evening_message_task_updates_roles(self):
        """
        Verify that the evening message task updates scores and roles.
        """
        # Call the task's coroutine with the mocked bot instance
        await self.evening_task_coro(self.bot, silent=True)

        # Assert that scores were updated
        self.bot.game.update_scores.assert_called_once()

        # Assert that the RolesCog was retrieved
        self.bot.get_cog.assert_called_with("RolesCog")

        # Assert that the role update logic was called
        self.roles_cog.roles_game_mode.run.assert_called_once()
        self.roles_cog.apply_discord_roles.assert_awaited_once_with(self.bot.guilds[0])


if __name__ == "__main__":
    unittest.main()
