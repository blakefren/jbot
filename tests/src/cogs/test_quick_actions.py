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
    """Tests for the GameActionView main button view and answer modal."""

    async def asyncSetUp(self):
        """Set up async test fixtures."""
        self.mock_bot = MagicMock()
        self.mock_bot.game = MagicMock()
        self.mock_bot.game.daily_q = MagicMock(question="What is 2+2?")
        mock_powerup_manager = MagicMock()
        # Mock the can_answer, can_rest, can_use_attack_powerup to return (True, "") by default
        mock_powerup_manager.can_answer = MagicMock(return_value=(True, ""))
        mock_powerup_manager.can_rest = MagicMock(return_value=(True, ""))
        mock_powerup_manager.can_use_attack_powerup = MagicMock(return_value=(True, ""))
        self.mock_bot.game.managers = {"powerup": mock_powerup_manager}

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

    async def test_answer_button_limits_previous_guesses_placeholder(self):
        self.mock_bot.game.daily_question_id = 42
        self.mock_bot.game.data_manager.read_guess_history.return_value = [
            {"guess_text": "wrong guess " + str(i)} for i in range(20)
        ]
        interaction = AsyncMock()
        interaction.user.id = 123
        view = GameActionView(self.mock_bot)
        button = next(
            item for item in view.children if item.custom_id == "trivia:answer"
        )

        await button.callback(interaction)

        modal = interaction.response.send_modal.call_args.args[0]
        self.assertIsInstance(modal, AnswerModal)
        self.assertLessEqual(len(modal.answer_input.placeholder), 100)
        self.assertIn("(truncated)", modal.answer_input.placeholder)
        self.mock_bot.game.data_manager.read_guess_history.assert_called_once_with(
            user_id=123, daily_question_id=42
        )

    async def test_answer_modal_placeholder_boundary_and_long_single_guess(self):
        self.mock_bot.game.daily_question_id = 42
        prefix = "Your previous guesses:\n1. "
        for guess_length in (100 - len(prefix), 500):
            with self.subTest(guess_length=guess_length):
                self.mock_bot.game.data_manager.read_guess_history.return_value = [
                    {"guess_text": "x" * guess_length}
                ]
                modal = AnswerModal(self.mock_bot, "Question", 123)
                placeholder = modal.answer_input.placeholder
                self.assertLessEqual(len(placeholder), 100)
                self.assertEqual("(truncated)" in placeholder, guess_length == 500)

    async def test_answer_modal_long_history_still_sends_feedback_and_announcement(
        self,
    ):
        self.mock_bot.game.daily_question_id = 42
        self.mock_bot.game.daily_q.answer = "correct"
        self.mock_bot.game.data_manager.read_guess_history.return_value = [
            {"guess_text": f"guess {i:03d} " + "x" * 100} for i in range(30)
        ]
        for is_correct in (False, True):
            with self.subTest(is_correct=is_correct):
                self.mock_bot.game.handle_guess.return_value = (is_correct, 30, 100, [])
                interaction = AsyncMock()
                interaction.user.id = 123
                interaction.user.display_name = "Player"
                modal = AnswerModal(self.mock_bot, "Question", 123)
                modal.answer_input._value = "guess"

                await modal.on_submit(interaction)

                message = interaction.followup.send.call_args.args[0]
                self.assertLessEqual(len(message), 2000)
                self.assertIn("(truncated)", message)
                self.assertIn("Correct!" if is_correct else "incorrect", message)
                if is_correct:
                    interaction.channel.send.assert_awaited_once()
                else:
                    interaction.channel.send.assert_not_awaited()

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

    async def test_admin_button_permission_denied(self):
        """Test admin button denies access to non-admins."""
        view = GameActionView(self.mock_bot)

        button = None
        for item in view.children:
            if hasattr(item, "custom_id") and item.custom_id == "trivia:admin":
                button = item
                break

        self.assertIsNotNone(button)
        mock_interaction = AsyncMock()
        mock_interaction.user.guild_permissions.administrator = False
        await button.callback(mock_interaction)
        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        self.assertIn(
            "permission", call_args[1].get("ephemeral", True) and str(call_args).lower()
        )

    async def test_admin_button_shows_menu(self):
        """Test admin button shows admin menu for admins."""
        view = GameActionView(self.mock_bot)

        button = None
        for item in view.children:
            if hasattr(item, "custom_id") and item.custom_id == "trivia:admin":
                button = item
                break

        self.assertIsNotNone(button)
        mock_interaction = AsyncMock()
        mock_interaction.user.guild_permissions.administrator = True
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
        expected_ids = {
            "trivia:answer",
            "trivia:jinx",
            "trivia:steal",
            "trivia:rest",
            "trivia:admin",
        }
        self.assertEqual(custom_ids, expected_ids)


if __name__ == "__main__":
    unittest.main()
