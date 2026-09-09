import unittest
from unittest.mock import AsyncMock, MagicMock
from src.cogs.answer_modal import AnswerModal, AnswerView


class TestAnswerViewButtonCallback(unittest.IsolatedAsyncioTestCase):
    """Tests for the AnswerView button callback.

    Note: Direct testing of AnswerModal.on_submit() is challenging due to Discord.py's
    TextInput property being read-only. The on_submit() logic (error handling, guess
    processing, response formatting) is tested through integration tests and manual testing.
    These tests focus on the button interaction and modal creation logic.
    """

    async def asyncSetUp(self):
        """Set up async test fixtures."""
        self.mock_bot = MagicMock()
        self.mock_bot.game = MagicMock()
        self.mock_bot.game.daily_q = MagicMock(question="What is 2+2?")

    async def test_button_callback_no_question(self):
        """Test button callback when no question is active."""
        self.mock_bot.game.daily_q = None
        view = AnswerView(self.mock_bot)
        # Get the button from the view
        button = None
        for item in view.children:
            if hasattr(item, "callback"):
                button = item
                break

        self.assertIsNotNone(button, "Button should exist in view")
        mock_interaction = AsyncMock()

        # Execute
        await button.callback(mock_interaction)

        # Verify that send_message was called (not send_modal)
        mock_interaction.response.send_message.assert_called_once()
        self.assertIn(
            "no active question",
            mock_interaction.response.send_message.call_args[0][0].lower(),
        )

    async def test_button_callback_with_question(self):
        """Test button callback when question is active."""
        self.mock_bot.game.daily_q = MagicMock(question="What is 2+2?")
        view = AnswerView(self.mock_bot)

        # Get the button from the view
        button = None
        for item in view.children:
            if hasattr(item, "callback"):
                button = item
                break

        self.assertIsNotNone(button, "Button should exist in view")
        mock_interaction = AsyncMock()

        # Execute
        await button.callback(mock_interaction)

        # Verify that send_modal was called with an AnswerModal
        mock_interaction.response.send_modal.assert_called_once()
        modal_arg = mock_interaction.response.send_modal.call_args[0][0]
        self.assertIsInstance(modal_arg, AnswerModal)

    async def test_view_persistent_button(self):
        """Test that view has persistent button with correct custom_id."""
        view = AnswerView(self.mock_bot)

        # Verify timeout is None for persistence across restarts
        self.assertIsNone(view.timeout, "View timeout should be None for persistence")

        # Get the button and verify its properties
        button = None
        for item in view.children:
            if hasattr(item, "custom_id"):
                button = item
                break

        self.assertIsNotNone(button, "Button should exist in view")
        self.assertEqual(button.custom_id, "trivia:answer")
        self.assertEqual(button.label, "Answer")


if __name__ == "__main__":
    unittest.main()
