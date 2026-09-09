import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from src.cogs.answer_modal import AnswerModal, AnswerView
from src.core.guess_handler import AlreadyAnsweredCorrectlyError, JinxedError


class TestAnswerModal(unittest.TestCase):
    """Tests for the AnswerModal class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_bot = MagicMock()
        self.mock_bot.game = MagicMock()
        self.mock_bot.game.daily_q = MagicMock(question="What is 2+2?", answer="4")
        self.mock_bot.game.daily_question_id = 1
        self.modal = AnswerModal(self.mock_bot, "What is 2+2?")

    def test_modal_creation(self):
        """Test that the modal is created with correct properties."""
        self.assertEqual(self.modal.title, "Submit Your Answer")
        self.assertEqual(self.modal.timeout, 300)
        self.assertIsNotNone(self.modal.answer_input)

    def test_modal_input_field_properties(self):
        """Test that the input field has correct properties."""
        self.assertEqual(self.modal.answer_input.label, "Your Answer")
        self.assertEqual(
            self.modal.answer_input.placeholder, "Type your answer here..."
        )
        self.assertTrue(self.modal.answer_input.required)
        self.assertEqual(self.modal.answer_input.max_length, 500)

    @patch("src.cogs.answer_modal.ConfigReader")
    async def test_modal_submit_correct_answer(self, mock_config):
        """Test modal submission with a correct answer."""
        # Setup
        self.mock_bot.game.handle_guess = MagicMock(return_value=(True, 1, 20, []))
        self.mock_bot.game.data_manager = MagicMock()
        self.mock_bot.game.data_manager.read_guess_history = MagicMock(
            return_value=[{"guess_text": "4", "daily_question_id": 1}]
        )

        mock_interaction = AsyncMock()
        mock_interaction.user.id = 12345
        mock_interaction.user.display_name = "TestUser"
        mock_interaction.channel = MagicMock()

        # Set answer input value
        self.modal.answer_input.value = "4"

        # Execute
        await self.modal.on_submit(mock_interaction)

        # Verify
        mock_interaction.response.defer.assert_called_once_with(ephemeral=True)
        self.mock_bot.game.handle_guess.assert_called_once_with(12345, "TestUser", "4")
        mock_interaction.followup.send.assert_called()

    @patch("src.cogs.answer_modal.ConfigReader")
    async def test_modal_submit_already_answered(self, mock_config):
        """Test modal submission when player already answered."""
        # Setup
        self.mock_bot.game.handle_guess = MagicMock(
            side_effect=AlreadyAnsweredCorrectlyError()
        )

        mock_interaction = AsyncMock()
        mock_interaction.user.id = 12345
        mock_interaction.user.display_name = "TestUser"

        self.modal.answer_input.value = "4"

        # Execute
        await self.modal.on_submit(mock_interaction)

        # Verify
        calls = mock_interaction.followup.send.call_args_list
        self.assertTrue(any("already solved" in str(call).lower() for call in calls))

    @patch("src.cogs.answer_modal.ConfigReader")
    async def test_modal_submit_jinxed(self, mock_config):
        """Test modal submission when player is jinxed."""
        mock_config_instance = MagicMock()
        mock_config_instance.get = MagicMock(return_value="🤐")
        mock_config.return_value = mock_config_instance

        # Setup
        error = JinxedError()
        error.message = "You are jinxed!"
        self.mock_bot.game.handle_guess = MagicMock(side_effect=error)

        mock_interaction = AsyncMock()
        mock_interaction.user.id = 12345
        mock_interaction.user.display_name = "TestUser"

        self.modal.answer_input.value = "4"

        # Execute
        await self.modal.on_submit(mock_interaction)

        # Verify
        calls = mock_interaction.followup.send.call_args_list
        self.assertTrue(any("jinxed" in str(call).lower() for call in calls))


class TestAnswerView(unittest.TestCase):
    """Tests for the AnswerView class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_bot = MagicMock()
        self.mock_bot.game = MagicMock()
        self.mock_bot.game.daily_q = MagicMock(question="What is 2+2?", answer="4")
        self.view = AnswerView(self.mock_bot)

    def test_view_creation(self):
        """Test that the view is created with correct properties."""
        self.assertIsNone(self.view.timeout)  # No timeout for persistence
        self.assertEqual(self.view.bot, self.mock_bot)

    def test_view_has_button(self):
        """Test that the view has an answer button."""
        buttons = [
            item for item in self.view.children if isinstance(item, discord.ui.Button)
        ]
        self.assertEqual(len(buttons), 1)
        button = buttons[0]
        self.assertEqual(button.label, "Answer Question")
        self.assertEqual(button.style, discord.ButtonStyle.primary)
        self.assertEqual(button.custom_id, "trivia:answer")

    async def test_button_callback_no_question(self):
        """Test button callback when no question is active."""
        self.mock_bot.game.daily_q = None
        button = [
            item for item in self.view.children if isinstance(item, discord.ui.Button)
        ][0]

        mock_interaction = AsyncMock()

        # Execute
        await button.callback(mock_interaction)

        # Verify
        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        self.assertIn("no active question", str(call_args).lower())

    async def test_button_callback_with_question(self):
        """Test button callback when question is active."""
        self.mock_bot.game.daily_q = MagicMock(question="What is 2+2?")
        button = [
            item for item in self.view.children if isinstance(item, discord.ui.Button)
        ][0]

        mock_interaction = AsyncMock()

        # Execute
        await button.callback(mock_interaction)

        # Verify
        mock_interaction.response.send_modal.assert_called_once()
        modal_arg = mock_interaction.response.send_modal.call_args[0][0]
        self.assertIsInstance(modal_arg, AnswerModal)


if __name__ == "__main__":
    unittest.main()
