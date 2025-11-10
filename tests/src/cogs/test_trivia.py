import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock, call


from src.core.discord import DiscordBot
from src.cogs.trivia import Trivia
from src.cfg.main import ConfigReader
from src.core.game_runner import GameRunner, AlreadyAnsweredCorrectlyError
from src.core.data_manager import DataManager


class TestTriviaCog(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_game_runner = MagicMock(spec=GameRunner)
        self.mock_config_reader = MagicMock(spec=ConfigReader)
        self.mock_data_manager = MagicMock(spec=DataManager)
        self.mock_game_runner.data_manager = self.mock_data_manager
        self.mock_game_runner.handle_guess = MagicMock()

        self.bot = MagicMock(spec=DiscordBot)
        self.bot.game = self.mock_game_runner
        self.bot.config = self.mock_config_reader
        self.bot.data_manager = self.mock_data_manager
        self.bot.send_message = AsyncMock()
        self.bot.is_owner = AsyncMock(return_value=True)

        self.trivia_cog = Trivia(self.bot)

    async def test_answer_command_correct(self):
        """Test the answer command with a correct guess."""
        await self.asyncSetUp()
        mock_ctx = AsyncMock()
        mock_ctx.author.id = 123
        mock_ctx.author.display_name = "Test User"
        mock_ctx.author.mention = "<@123>"

        # Mock the return value of handle_guess to be (is_correct, num_guesses)
        self.mock_game_runner.handle_guess.return_value = (True, 1)
        self.mock_game_runner.get_player_guesses.return_value = ["test answer"]
        self.mock_game_runner.daily_q = MagicMock()

        await self.trivia_cog.answer.callback(
            self.trivia_cog, mock_ctx, guess="test answer"
        )

        self.mock_game_runner.handle_guess.assert_called_once_with(
            123, "Test User", "test answer"
        )

        # Check for the two calls to send_message
        mock_ctx.interaction.followup.send.assert_called_once_with(
            "That is correct! Nicely done.\n\nYour guesses:\n1. test answer"
        )
        mock_ctx.channel.send.assert_called_once_with(
            f"{mock_ctx.author.mention} got the correct answer in 1 guess(es)!"
        )

    async def test_answer_command_incorrect(self):
        """Test the answer command with an incorrect guess."""
        await self.asyncSetUp()
        mock_ctx = AsyncMock()
        mock_ctx.author.id = 123
        mock_ctx.author.display_name = "Test User"

        self.mock_game_runner.handle_guess.return_value = (False, 2)
        self.mock_game_runner.get_player_guesses.return_value = ["wrong answer"]
        self.mock_game_runner.daily_q = MagicMock()

        await self.trivia_cog.answer.callback(
            self.trivia_cog, mock_ctx, guess="wrong answer"
        )

        self.mock_game_runner.handle_guess.assert_called_once_with(
            123, "Test User", "wrong answer"
        )
        mock_ctx.interaction.followup.send.assert_called_once_with(
            "Sorry, that is not the correct answer.\n\nYour guesses:\n1. wrong answer"
        )

    async def test_answer_command_no_question(self):
        """Test the answer command when there is no active question."""
        await self.asyncSetUp()
        mock_ctx = AsyncMock()
        self.mock_game_runner.daily_q = None

        await self.trivia_cog.answer.callback(
            self.trivia_cog, mock_ctx, guess="any answer"
        )

        self.mock_game_runner.handle_guess.assert_not_called()
        mock_ctx.interaction.followup.send.assert_called_once_with(
            "There is no active question right now."
        )

    async def test_answer_command_already_answered_correctly(self):
        """Test the answer command when the player has already answered correctly."""
        await self.asyncSetUp()
        mock_ctx = AsyncMock()
        mock_ctx.author.id = 123
        mock_ctx.author.display_name = "Test User"
        self.mock_game_runner.daily_q = MagicMock()

        # Configure the mock to raise the custom exception
        self.mock_game_runner.handle_guess.side_effect = AlreadyAnsweredCorrectlyError

        await self.trivia_cog.answer.callback(
            self.trivia_cog, mock_ctx, guess="any guess"
        )

        # Verify handle_guess was called
        self.mock_game_runner.handle_guess.assert_called_once_with(
            123, "Test User", "any guess"
        )

        # Check that the correct feedback is sent
        mock_ctx.interaction.followup.send.assert_called_once_with(
            "You have already answered today's question correctly."
        )

        # Ensure no other messages were sent
        mock_ctx.channel.send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
