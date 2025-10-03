import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from bot.discord import DiscordBot, set_bot_commands
from cfg.main import ConfigReader
from modes.game_runner import GameRunner
from database.logger import Logger


class TestDiscordBot(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_game_runner = MagicMock(spec=GameRunner)
        self.mock_config_reader = MagicMock(spec=ConfigReader)
        self.mock_logger = MagicMock(spec=Logger)
        self.mock_game_runner.logger = self.mock_logger
        self.mock_game_runner.handle_guess = MagicMock()

        self.bot = DiscordBot(
            bot_token="test_token",
            game=self.mock_game_runner,
            config=self.mock_config_reader,
        )
        self.bot.send_message = AsyncMock()
        set_bot_commands(self.bot)
        self.bot.is_owner = AsyncMock(return_value=True)

    async def test_answer_command_correct(self):
        """Test the answer command with a correct guess."""
        mock_ctx = AsyncMock()
        mock_ctx.author.id = 123
        mock_ctx.author.display_name = "Test User"

        self.mock_game_runner.handle_guess.return_value = True
        self.mock_game_runner.daily_q = MagicMock()

        answer_command = self.bot.get_command("answer")
        await answer_command.callback(mock_ctx, guess="test answer")

        self.mock_game_runner.handle_guess.assert_called_once_with(
            123, "Test User", "test answer"
        )
        self.bot.send_message.assert_called_once_with(
            "That is correct! Nicely done.", ctx=mock_ctx
        )

    async def test_answer_command_incorrect(self):
        """Test the answer command with an incorrect guess."""
        mock_ctx = AsyncMock()
        mock_ctx.author.id = 123
        mock_ctx.author.display_name = "Test User"

        self.mock_game_runner.handle_guess.return_value = False
        self.mock_game_runner.daily_q = MagicMock()

        answer_command = self.bot.get_command("answer")
        await answer_command.callback(mock_ctx, guess="wrong answer")

        self.mock_game_runner.handle_guess.assert_called_once_with(
            123, "Test User", "wrong answer"
        )
        self.bot.send_message.assert_called_once_with(
            "Sorry, that is not the correct answer.", ctx=mock_ctx
        )

    async def test_answer_command_no_question(self):
        """Test the answer command when there is no active question."""
        mock_ctx = AsyncMock()
        self.mock_game_runner.daily_q = None

        answer_command = self.bot.get_command("answer")
        await answer_command.callback(mock_ctx, guess="any answer")

        self.mock_game_runner.handle_guess.assert_not_called()
        self.bot.send_message.assert_called_once_with(
            "There is no active question right now.", ctx=mock_ctx
        )


if __name__ == "__main__":
    unittest.main()
