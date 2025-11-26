import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import sys

from src.cogs.utils import Utils, get_powerup_manager


class TestGetPowerupManager(unittest.IsolatedAsyncioTestCase):
    async def test_get_powerup_manager_not_powerup_mode(self):
        """Test that get_powerup_manager returns None when not in POWERUP mode."""
        bot = MagicMock()
        bot.game = MagicMock()
        bot.game.mode.name = "NORMAL"
        bot.send_message = AsyncMock()
        interaction = MagicMock()

        result = await get_powerup_manager(bot, interaction)

        self.assertIsNone(result)
        bot.send_message.assert_called_once_with(
            "This command is only available in POWERUP mode.",
            interaction=interaction,
            ephemeral=True,
        )

    async def test_get_powerup_manager_in_powerup_mode(self):
        """Test that get_powerup_manager returns a PowerUpManager when in POWERUP mode."""
        bot = MagicMock()
        bot.game = MagicMock()
        bot.game.mode.name = "POWERUP"
        bot.player_manager = MagicMock()
        bot.player_manager.get_all_players.return_value = {"player1": MagicMock()}
        interaction = MagicMock()

        result = await get_powerup_manager(bot, interaction)

        self.assertIsNotNone(result)
        bot.player_manager.get_all_players.assert_called_once()


class TestUtilsCog(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.send_message = AsyncMock()
        self.bot.close = AsyncMock()

        # Mock tasks
        self.bot.morning_message_task = MagicMock()
        self.bot.morning_message_task.is_running.return_value = True
        self.bot.morning_message_task.cancel = MagicMock()

        self.bot.reminder_message_task = MagicMock()
        self.bot.reminder_message_task.is_running.return_value = True
        self.bot.reminder_message_task.cancel = MagicMock()

        self.bot.evening_message_task = MagicMock()
        self.bot.evening_message_task.is_running.return_value = True
        self.bot.evening_message_task.cancel = MagicMock()

        # Mock data_manager
        self.bot.data_manager = MagicMock()
        self.bot.data_manager.db = MagicMock()
        self.bot.data_manager.db.conn = MagicMock()
        self.bot.data_manager.db.close = MagicMock()

        self.cog = Utils(self.bot)

        self.ctx = MagicMock()
        self.ctx.interaction = MagicMock()
        self.ctx.channel = MagicMock()
        self.ctx.channel.id = 12345
        self.ctx.author = MagicMock()
        self.ctx.author.id = 67890

    async def test_ping_command(self):
        """Test the ping command returns Pong!"""
        await self.cog.ping.callback(self.cog, self.ctx)

        self.bot.send_message.assert_called_once_with(
            "Pong!", interaction=self.ctx.interaction
        )

    @patch("sys.exit")
    @patch("builtins.open", new_callable=MagicMock)
    async def test_shutdown_without_restart(self, mock_open, mock_exit):
        """Test the shutdown command without restart."""
        await self.cog.shutdown.callback(self.cog, self.ctx, restart=False)

        # Verify message was sent
        self.bot.send_message.assert_called_once_with(
            "Shutting down...", interaction=self.ctx.interaction
        )

        # Verify tasks were cancelled
        self.bot.morning_message_task.cancel.assert_called_once()
        self.bot.reminder_message_task.cancel.assert_called_once()
        self.bot.evening_message_task.cancel.assert_called_once()

        # Verify database was closed
        self.bot.data_manager.db.close.assert_called_once()

        # Verify bot was closed
        self.bot.close.assert_called_once()

        # Verify sys.exit was called
        mock_exit.assert_called_once_with(0)

    @patch("sys.exit")
    @patch("builtins.open", new_callable=MagicMock)
    async def test_shutdown_with_restart(self, mock_open, mock_exit):
        """Test the shutdown command with restart."""
        await self.cog.shutdown.callback(self.cog, self.ctx, restart=True)

        # Verify restart info file was written
        mock_open.assert_called_once_with("restart.inf", "w")
        mock_file = mock_open.return_value.__enter__.return_value
        mock_file.write.assert_called_once_with(
            f"{self.ctx.channel.id},{self.ctx.author.id}"
        )

        # Verify message was sent
        self.bot.send_message.assert_called_once_with(
            "Restarting bot...", interaction=self.ctx.interaction
        )

        # Verify tasks were cancelled
        self.bot.morning_message_task.cancel.assert_called_once()
        self.bot.reminder_message_task.cancel.assert_called_once()
        self.bot.evening_message_task.cancel.assert_called_once()

        # Verify bot was closed
        self.bot.close.assert_called_once()

    @patch("sys.exit")
    @patch("builtins.open", new_callable=MagicMock)
    async def test_shutdown_tasks_not_running(self, mock_open, mock_exit):
        """Test shutdown when tasks are not running."""
        self.bot.morning_message_task.is_running.return_value = False
        self.bot.reminder_message_task.is_running.return_value = False
        self.bot.evening_message_task.is_running.return_value = False

        await self.cog.shutdown.callback(self.cog, self.ctx, restart=False)

        # Verify tasks were not cancelled since they weren't running
        self.bot.morning_message_task.cancel.assert_not_called()
        self.bot.reminder_message_task.cancel.assert_not_called()
        self.bot.evening_message_task.cancel.assert_not_called()

        # But bot should still close
        self.bot.close.assert_called_once()


class TestUtilsSetup(unittest.IsolatedAsyncioTestCase):
    async def test_setup(self):
        """Test that the setup function adds the cog."""
        from src.cogs.utils import setup

        mock_bot = MagicMock()
        mock_bot.add_cog = AsyncMock()

        await setup(mock_bot)

        mock_bot.add_cog.assert_called_once()
        # Verify it's a Utils instance
        call_args = mock_bot.add_cog.call_args
        self.assertIsInstance(call_args[0][0], Utils)


if __name__ == "__main__":
    unittest.main()
