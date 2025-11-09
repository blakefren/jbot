import unittest
from unittest.mock import AsyncMock, MagicMock
import discord

from src.cogs.admin import Admin
from src.cfg.players import PlayerManager
from src.core.game_runner import GameRunner
from db.database import Database

class TestAdminCog(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.morning_message_task = AsyncMock()
        self.bot.reminder_message_task = AsyncMock()
        self.bot.evening_message_task = AsyncMock()

        # Mocks for refund test
        self.bot.game = MagicMock(spec=GameRunner)
        self.bot.game.player_manager = MagicMock(spec=PlayerManager)
        self.bot.data_manager = MagicMock()
        self.bot.data_manager.db = MagicMock(spec=Database)
        
        self.cog = Admin(self.bot)
        
        self.ctx = MagicMock()
        self.ctx.defer = AsyncMock()
        self.ctx.send = AsyncMock()
        self.ctx.author = MagicMock()
        self.ctx.author.id = "admin_id_456"

    async def test_resend_morning_silent(self):
        """Tests resend command for morning message with silent=True."""
        await self.cog.resend.callback(self.cog, self.ctx, message_type="morning", silent=True)
        
        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_called_once_with(silent=True)
        self.bot.reminder_message_task.assert_not_called()
        self.bot.evening_message_task.assert_not_called()
        self.ctx.send.assert_called_once_with("Silently resent morning message.", ephemeral=True)

    async def test_resend_morning_not_silent(self):
        """Tests resend command for morning message with silent=False."""
        await self.cog.resend.callback(self.cog, self.ctx, message_type="morning", silent=False)
        
        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_called_once_with(silent=False)
        self.bot.reminder_message_task.assert_not_called()
        self.bot.evening_message_task.assert_not_called()
        self.ctx.send.assert_called_once_with("Morning message resent.")

    async def test_resend_reminder_silent(self):
        """Tests resend command for reminder message with silent=True."""
        await self.cog.resend.callback(self.cog, self.ctx, message_type="reminder", silent=True)
        
        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_not_called()
        self.bot.reminder_message_task.assert_called_once_with(silent=True)
        self.bot.evening_message_task.assert_not_called()
        self.ctx.send.assert_called_once_with("Silently resent reminder message.", ephemeral=True)

    async def test_resend_reminder_not_silent(self):
        """Tests resend command for reminder message with silent=False."""
        await self.cog.resend.callback(self.cog, self.ctx, message_type="reminder", silent=False)
        
        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_not_called()
        self.bot.reminder_message_task.assert_called_once_with(silent=False)
        self.bot.evening_message_task.assert_not_called()
        self.ctx.send.assert_called_once_with("Reminder message resent.")

    async def test_resend_evening_silent(self):
        """Tests resend command for evening message with silent=True."""
        await self.cog.resend.callback(self.cog, self.ctx, message_type="evening", silent=True)
        
        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_not_called()
        self.bot.reminder_message_task.assert_not_called()
        self.bot.evening_message_task.assert_called_once_with(silent=True)
        self.ctx.send.assert_called_once_with("Silently resent evening message.", ephemeral=True)

    async def test_resend_evening_not_silent(self):
        """Tests resend command for evening message with silent=False."""
        await self.cog.resend.callback(self.cog, self.ctx, message_type="evening", silent=False)
        
        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_not_called()
        self.bot.reminder_message_task.assert_not_called()
        self.bot.evening_message_task.assert_called_once_with(silent=False)
        self.ctx.send.assert_called_once_with("Evening message resent.")

    async def test_resend_invalid_message_type(self):
        """Tests resend command with an invalid message type."""
        await self.cog.resend.callback(self.cog, self.ctx, message_type="invalid", silent=False)
        
        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_not_called()
        self.bot.reminder_message_task.assert_not_called()
        self.bot.evening_message_task.assert_not_called()
        self.ctx.send.assert_called_once_with("Invalid message type. Use 'morning', 'reminder', or 'evening'.")

    async def test_refund_reloads_player_data(self):
        """
        Test that the refund command correctly calls reload_players.
        """
        # Setup mocks
        member = MagicMock(spec=discord.Member)
        member.id = "player_id_123"
        member.display_name = "TestPlayer"
        
        amount = 50
        reason = "Test refund"

        # Configure the mock player_manager
        player_manager = self.bot.game.player_manager
        
        # get_player is called twice. First to get the player, second to get the updated score for the message.
        # We'll have it return a different mock each time to simulate the data changing.
        mock_player_before_refund = MagicMock()
        mock_player_after_refund = MagicMock()
        mock_player_after_refund.__getitem__.side_effect = lambda key: {'score': 150}[key]

        player_manager.get_player.side_effect = [
            mock_player_before_refund,
            mock_player_after_refund
        ]

        # Call the refund command
        await self.cog.refund.callback(self.cog, self.ctx, member, amount, reason=reason)

        # Assertions
        player_manager.refund_score.assert_called_once_with(str(member.id), amount)
        self.bot.data_manager.log_score_adjustment.assert_called_once_with(
            player_id=str(member.id),
            admin_id=str(self.ctx.author.id),
            amount=amount,
            reason=reason
        )
        player_manager.reload_players.assert_called_once()
        
        # Verify get_player was called twice
        self.assertEqual(player_manager.get_player.call_count, 2)

        # Check the final message
        expected_message = f"Refunded {amount} to {member.display_name}. New score: 150. Reason: {reason}"
        self.ctx.send.assert_called_once_with(expected_message)

if __name__ == '__main__':
    unittest.main()
