import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock, call
from datetime import datetime, timezone


from src.core.discord import DiscordBot
from src.cogs.trivia import Trivia
from src.cfg.main import ConfigReader
from src.core.game_runner import GameRunner
from src.core.guess_handler import AlreadyAnsweredCorrectlyError
from src.core.data_manager import DataManager


class TestTriviaCog(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_game_runner = MagicMock(spec=GameRunner)
        self.mock_config_reader = MagicMock(spec=ConfigReader)
        self.mock_data_manager = MagicMock(spec=DataManager)
        self.mock_game_runner.data_manager = self.mock_data_manager
        self.mock_game_runner.handle_guess = MagicMock()
        self.mock_game_runner.question_selector = MagicMock()

        self.bot = MagicMock(spec=DiscordBot)
        self.bot.game = self.mock_game_runner
        self.bot.config = self.mock_config_reader
        self.bot.data_manager = self.mock_data_manager
        self.bot.send_message = AsyncMock()
        self.bot.is_owner = AsyncMock(return_value=True)

        # Mock tasks for when command
        self.bot.morning_message_task = MagicMock()
        self.bot.evening_message_task = MagicMock()

        self.trivia_cog = Trivia(self.bot)

    async def test_answer_command_correct(self):
        """Test the answer command with a correct guess."""
        await self.asyncSetUp()
        mock_ctx = AsyncMock()
        mock_ctx.author.id = 123
        mock_ctx.author.display_name = "Test User"
        mock_ctx.author.mention = "<@123>"

        # Mock the return value of handle_guess to be (is_correct, num_guesses, points, bonuses)
        self.mock_game_runner.handle_guess.return_value = (True, 1, 100, [])
        self.mock_game_runner.daily_q = MagicMock()
        self.mock_game_runner.daily_question_id = 1
        self.mock_data_manager.read_guess_history.return_value = [
            {"guess_text": "test answer", "daily_question_id": 1}
        ]

        await self.trivia_cog.answer.callback(
            self.trivia_cog, mock_ctx, guess="test answer"
        )

        self.mock_game_runner.handle_guess.assert_called_once_with(
            123, "Test User", "test answer"
        )

        # Check for the two calls to send_message
        mock_ctx.interaction.followup.send.assert_called_once_with(
            "Correct! Nicely done.\n\nGuesses:\n1. test answer"
        )
        mock_ctx.channel.send.assert_called_once_with(
            f"{mock_ctx.author.mention} solved it in 1! (+**100** pts)"
        )

    async def test_answer_command_incorrect(self):
        """Test the answer command with an incorrect guess."""
        await self.asyncSetUp()
        mock_ctx = AsyncMock()
        mock_ctx.author.id = 123
        mock_ctx.author.display_name = "Test User"

        self.mock_game_runner.handle_guess.return_value = (False, 2, 0, [])
        self.mock_game_runner.daily_q = MagicMock()
        self.mock_game_runner.daily_question_id = 1
        self.mock_data_manager.read_guess_history.return_value = [
            {"guess_text": "wrong answer", "daily_question_id": 1}
        ]

        await self.trivia_cog.answer.callback(
            self.trivia_cog, mock_ctx, guess="wrong answer"
        )

        self.mock_game_runner.handle_guess.assert_called_once_with(
            123, "Test User", "wrong answer"
        )
        mock_ctx.interaction.followup.send.assert_called_once_with(
            "Sorry, that was incorrect.\n\nGuesses:\n1. wrong answer"
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
            "There is no active question."
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
            "You already solved today."
        )

        # Ensure no other messages were sent
        mock_ctx.channel.send.assert_not_called()

    async def test_answer_command_no_daily_question_id(self):
        """Test the answer command when there's no daily_question_id."""
        await self.asyncSetUp()
        mock_ctx = AsyncMock()
        mock_ctx.author.id = 123
        mock_ctx.author.display_name = "Test User"

        self.mock_game_runner.handle_guess.return_value = (True, 1, 100, [])
        self.mock_game_runner.daily_q = MagicMock()
        self.mock_game_runner.daily_question_id = None  # No daily_question_id

        await self.trivia_cog.answer.callback(
            self.trivia_cog, mock_ctx, guess="test answer"
        )

        # Should still work, just with empty guesses
        mock_ctx.interaction.followup.send.assert_called_once()
        args = mock_ctx.interaction.followup.send.call_args[0][0]
        assert "Correct!" in args
        assert "No guesses yet." in args

    async def test_answer_command_generic_exception(self):
        """Test the answer command handles generic exceptions."""
        await self.asyncSetUp()
        mock_ctx = AsyncMock()
        mock_ctx.author.id = 123
        mock_ctx.author.display_name = "Test User"
        self.mock_game_runner.daily_q = MagicMock()

        # Configure the mock to raise a generic exception
        self.mock_game_runner.handle_guess.side_effect = Exception("Database error")

        await self.trivia_cog.answer.callback(
            self.trivia_cog, mock_ctx, guess="any guess"
        )

        mock_ctx.interaction.followup.send.assert_called_once_with(
            "An error occurred while processing your answer. Please try again later."
        )

    async def test_answer_command_multiple_guesses_deduplicated(self):
        """Test that duplicate guesses are deduplicated and sorted."""
        await self.asyncSetUp()
        mock_ctx = AsyncMock()
        mock_ctx.author.id = 123
        mock_ctx.author.display_name = "Test User"

        self.mock_game_runner.handle_guess.return_value = (False, 3, 0, [])
        self.mock_game_runner.daily_q = MagicMock()
        self.mock_game_runner.daily_question_id = 1
        # Return duplicate guesses that should be deduplicated
        self.mock_data_manager.read_guess_history.return_value = [
            {"guess_text": "Apple", "daily_question_id": 1},
            {"guess_text": "Banana", "daily_question_id": 1},
            {
                "guess_text": "apple",
                "daily_question_id": 1,
            },  # Duplicate (case-insensitive)
            {"guess_text": "Cherry", "daily_question_id": 1},
        ]

        await self.trivia_cog.answer.callback(self.trivia_cog, mock_ctx, guess="cherry")

        mock_ctx.interaction.followup.send.assert_called_once()
        args = mock_ctx.interaction.followup.send.call_args[0][0]
        # Should be deduplicated and sorted
        assert "apple" in args
        assert "banana" in args
        assert "cherry" in args

    async def test_answer_command_filters_by_daily_question_id(self):
        """Test that guesses are filtered by the current daily_question_id."""
        await self.asyncSetUp()
        mock_ctx = AsyncMock()
        mock_ctx.author.id = 123
        mock_ctx.author.display_name = "Test User"

        self.mock_game_runner.handle_guess.return_value = (False, 1, 0, [])
        self.mock_game_runner.daily_q = MagicMock()
        self.mock_game_runner.daily_question_id = 2  # Current question ID
        # Return guesses from multiple questions
        self.mock_data_manager.read_guess_history.return_value = [
            {"guess_text": "Old guess", "daily_question_id": 1},  # Different question
            {"guess_text": "Current guess", "daily_question_id": 2},  # Current question
        ]

        await self.trivia_cog.answer.callback(
            self.trivia_cog, mock_ctx, guess="current guess"
        )

        mock_ctx.interaction.followup.send.assert_called_once()
        args = mock_ctx.interaction.followup.send.call_args[0][0]
        # Should only show guesses for the current question
        assert "current guess" in args
        assert "Old guess" not in args


class TestTriviaSetup(unittest.IsolatedAsyncioTestCase):
    async def test_setup(self):
        """Test that the setup function adds the cog."""
        from src.cogs.trivia import setup

        mock_bot = MagicMock()
        mock_bot.add_cog = AsyncMock()

        await setup(mock_bot)

        mock_bot.add_cog.assert_called_once()
        call_args = mock_bot.add_cog.call_args
        self.assertIsInstance(call_args[0][0], Trivia)


if __name__ == "__main__":
    unittest.main()
