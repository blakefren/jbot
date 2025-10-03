import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from bot.discord import DiscordBot
from bot.cogs.trivia import Trivia
from cfg.main import ConfigReader
from modes.game_runner import GameRunner
from database.logger import Logger


class TestTriviaCog(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_game_runner = MagicMock(spec=GameRunner)
        self.mock_config_reader = MagicMock(spec=ConfigReader)
        self.mock_logger = MagicMock(spec=Logger)
        self.mock_game_runner.logger = self.mock_logger
        self.mock_game_runner.handle_guess = MagicMock()

        self.bot = MagicMock(spec=DiscordBot)
        self.bot.game = self.mock_game_runner
        self.bot.config = self.mock_config_reader
        self.bot.logger = self.mock_logger
        self.bot.send_message = AsyncMock()
        self.bot.is_owner = AsyncMock(return_value=True)

        self.trivia_cog = Trivia(self.bot)

    async def test_answer_command_correct(self):
        """Test the answer command with a correct guess."""
        await self.asyncSetUp()
        mock_ctx = AsyncMock()
        mock_ctx.author.id = 123
        mock_ctx.author.display_name = "Test User"

        self.mock_game_runner.handle_guess.return_value = True
        self.mock_game_runner.daily_q = MagicMock()

        await self.trivia_cog.answer.callback(self.trivia_cog, mock_ctx, guess="test answer")

        self.mock_game_runner.handle_guess.assert_called_once_with(
            123, "Test User", "test answer"
        )
        self.bot.send_message.assert_called_once_with(
            "That is correct! Nicely done.",
            interaction=mock_ctx.interaction,
            ephemeral=True,
        )

    async def test_answer_command_incorrect(self):
        """Test the answer command with an incorrect guess."""
        await self.asyncSetUp()
        mock_ctx = AsyncMock()
        mock_ctx.author.id = 123
        mock_ctx.author.display_name = "Test User"

        self.mock_game_runner.handle_guess.return_value = False
        self.mock_game_runner.daily_q = MagicMock()

        await self.trivia_cog.answer.callback(self.trivia_cog, mock_ctx, guess="wrong answer")

        self.mock_game_runner.handle_guess.assert_called_once_with(
            123, "Test User", "wrong answer"
        )
        self.bot.send_message.assert_called_once_with(
            "Sorry, that is not the correct answer.",
            interaction=mock_ctx.interaction,
            ephemeral=True,
        )

    async def test_answer_command_no_question(self):
        """Test the answer command when there is no active question."""
        await self.asyncSetUp()
        mock_ctx = AsyncMock()
        self.mock_game_runner.daily_q = None

        await self.trivia_cog.answer.callback(self.trivia_cog, mock_ctx, guess="any answer")

        self.mock_game_runner.handle_guess.assert_not_called()
        self.bot.send_message.assert_called_once_with(
            "There is no active question right now.",
            interaction=mock_ctx.interaction,
            ephemeral=True,
        )


if __name__ == "__main__":
    unittest.main()
