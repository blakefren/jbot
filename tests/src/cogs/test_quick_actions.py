import unittest
from unittest.mock import AsyncMock, MagicMock
from src.cogs.quick_actions import (
    AnswerModal,
    GameActionView,
    JinxSelectView,
    StealSelectView,
    RestConfirmationView,
)


class TestGameActionView(unittest.IsolatedAsyncioTestCase):
    """Tests for the GameActionView main button view.

    Note: Direct testing of AnswerModal.on_submit() is challenging due to Discord.py's
    TextInput property being read-only. The on_submit() logic (error handling, guess
    processing, response formatting) is tested through integration tests and manual testing.
    These tests focus on the button interaction and view/modal creation logic.
    """

    async def asyncSetUp(self):
        """Set up async test fixtures."""
        self.mock_bot = MagicMock()
        self.mock_bot.game = MagicMock()
        self.mock_bot.game.daily_q = MagicMock(question="What is 2+2?")
        self.mock_bot.game.managers = {"powerup": MagicMock()}

    async def test_answer_button_no_question(self):
        """Test answer button when no question is active."""
        self.mock_bot.game.daily_q = None
        view = GameActionView(self.mock_bot)
        # Get the answer button
        button = None
        for item in view.children:
            if hasattr(item, "custom_id") and item.custom_id == "trivia:answer":
                button = item
                break

        self.assertIsNotNone(button)
        mock_interaction = AsyncMock()
        await button.callback(mock_interaction)
        mock_interaction.response.send_message.assert_called_once()

    async def test_answer_button_with_question(self):
        """Test answer button opens modal with question displayed."""
        self.mock_bot.game.daily_q = MagicMock(question="What is 2+2?")
        view = GameActionView(self.mock_bot)

        button = None
        for item in view.children:
            if hasattr(item, "custom_id") and item.custom_id == "trivia:answer":
                button = item
                break

        self.assertIsNotNone(button)
        mock_interaction = AsyncMock()
        await button.callback(mock_interaction)
        # Verify modal is shown directly
        mock_interaction.response.send_modal.assert_called_once()

    async def test_jinx_button_shows_selection(self):
        """Test jinx button shows player selection view."""
        self.mock_bot.game.daily_q = MagicMock(question="What is 2+2?")
        self.mock_bot.game.player_manager = MagicMock()
        self.mock_bot.game.player_manager.get_all_players = MagicMock(return_value={})

        view = GameActionView(self.mock_bot)
        button = None
        for item in view.children:
            if hasattr(item, "custom_id") and item.custom_id == "trivia:jinx":
                button = item
                break

        self.assertIsNotNone(button)
        mock_interaction = AsyncMock()
        await button.callback(mock_interaction)
        mock_interaction.response.send_message.assert_called_once()

    async def test_steal_button_shows_selection(self):
        """Test steal button shows player selection view."""
        self.mock_bot.game.daily_q = MagicMock(question="What is 2+2?")
        self.mock_bot.game.player_manager = MagicMock()
        self.mock_bot.game.player_manager.get_all_players = MagicMock(return_value={})

        view = GameActionView(self.mock_bot)
        button = None
        for item in view.children:
            if hasattr(item, "custom_id") and item.custom_id == "trivia:steal":
                button = item
                break

        self.assertIsNotNone(button)
        mock_interaction = AsyncMock()
        await button.callback(mock_interaction)
        mock_interaction.response.send_message.assert_called_once()

    async def test_rest_button_shows_confirmation(self):
        """Test rest button shows confirmation view."""
        self.mock_bot.game.daily_q = MagicMock(question="What is 2+2?")
        view = GameActionView(self.mock_bot)

        button = None
        for item in view.children:
            if hasattr(item, "custom_id") and item.custom_id == "trivia:rest":
                button = item
                break

        self.assertIsNotNone(button)
        mock_interaction = AsyncMock()
        await button.callback(mock_interaction)
        mock_interaction.response.send_message.assert_called_once()

    async def test_view_persistent(self):
        """Test that GameActionView has no timeout for persistence."""
        view = GameActionView(self.mock_bot)
        self.assertIsNone(view.timeout)

    async def test_view_has_all_buttons(self):
        """Test that GameActionView has all expected buttons."""
        view = GameActionView(self.mock_bot)
        custom_ids = {
            item.custom_id for item in view.children if hasattr(item, "custom_id")
        }
        expected_ids = {"trivia:answer", "trivia:jinx", "trivia:steal", "trivia:rest"}
        self.assertEqual(custom_ids, expected_ids)


if __name__ == "__main__":
    unittest.main()
