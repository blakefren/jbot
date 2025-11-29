import unittest
from unittest.mock import MagicMock, AsyncMock

from data.readers.question import Question
from src.cogs.admin import Admin


class TestAdminCog(unittest.IsolatedAsyncioTestCase):
    async def test_skip_command_success(self):
        # Arrange
        mock_bot = MagicMock()
        mock_bot.game.daily_q = Question("q", "a", "c", 100)
        mock_bot.game.reset_daily_question.return_value = True
        mock_bot.game.format_question.return_value = "Formatted Question"

        mock_ctx = MagicMock()
        mock_ctx.defer = AsyncMock()
        mock_ctx.send = AsyncMock()

        admin_cog = Admin(mock_bot)

        # Act
        await admin_cog.skip.callback(admin_cog, mock_ctx)

        # Assert
        mock_ctx.defer.assert_called_once_with()
        mock_bot.game.reset_daily_question.assert_called_once()
        mock_ctx.send.assert_called_once_with(
            "The daily question has been skipped. The new question is:\nFormatted Question"
        )

    async def test_skip_command_no_active_question(self):
        # Arrange
        mock_bot = MagicMock()
        mock_bot.game.daily_q = None

        mock_ctx = MagicMock()
        mock_ctx.defer = AsyncMock()
        mock_ctx.send = AsyncMock()

        admin_cog = Admin(mock_bot)

        # Act
        await admin_cog.skip.callback(admin_cog, mock_ctx)

        # Assert
        mock_ctx.defer.assert_called_once_with()
        mock_bot.game.reset_daily_question.assert_not_called()
        mock_ctx.send.assert_called_once_with("There is no active question to skip.")

    async def test_skip_command_reset_fails(self):
        # Arrange
        mock_bot = MagicMock()
        mock_bot.game.daily_q = Question("q", "a", "c", 100)
        mock_bot.game.reset_daily_question.return_value = False

        mock_ctx = MagicMock()
        mock_ctx.defer = AsyncMock()
        mock_ctx.send = AsyncMock()

        admin_cog = Admin(mock_bot)

        # Act
        await admin_cog.skip.callback(admin_cog, mock_ctx)

        # Assert
        mock_ctx.defer.assert_called_once_with()
        mock_bot.game.reset_daily_question.assert_called_once()
        mock_ctx.send.assert_called_once_with(
            "Failed to skip the daily question. Check the logs."
        )


if __name__ == "__main__":
    unittest.main()
