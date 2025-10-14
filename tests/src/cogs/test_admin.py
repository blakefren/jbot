import unittest
from unittest.mock import AsyncMock, MagicMock

from src.cogs.admin import Admin

class TestAdminCog(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.morning_message_task = AsyncMock()
        self.bot.reminder_message_task = AsyncMock()
        self.bot.evening_message_task = AsyncMock()
        
        self.cog = Admin(self.bot)
        
        self.ctx = MagicMock()
        self.ctx.defer = AsyncMock()
        self.ctx.send = AsyncMock()

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

if __name__ == '__main__':
    unittest.main()
