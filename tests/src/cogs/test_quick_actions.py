import unittest
from unittest.mock import AsyncMock, MagicMock
from data.readers.question import Question
from src.cogs.quick_actions import (
    AddAnswerModal,
    AddAnswerConfirmationView,
    AnswerModal,
    GameActionView,
    JinxSelectView,
    RefundModal,
    RefundSelectView,
    SkipConfirmationView,
    StealSelectView,
    RestConfirmationView,
)
from src.core.data_manager import DataManager
from src.core.guess_handler import (
    AlreadyAnsweredCorrectlyError,
    GuessHandler,
    JinxedError,
)
from src.core.player_manager import PlayerManager
from src.core.powerup import PowerUpError, PowerUpManager
from db.database import Database
from tests.src.core._powerup_helpers import make_config


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

    async def test_answer_button_blocks_player_when_manager_denies_answer(self):
        self.mock_bot.game.daily_question_id = 42
        manager = self.mock_bot.game.managers["powerup"]
        manager.can_answer.return_value = (False, "You are silenced.")
        interaction = AsyncMock()
        interaction.user.id = 123

        with unittest.mock.patch("src.cogs.quick_actions.ConfigReader") as config:
            config.return_value.get.return_value = "🤐"
            view = GameActionView(self.mock_bot)
            button = next(
                child for child in view.children if child.custom_id == "trivia:answer"
            )
            await button.callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        interaction.response.send_modal.assert_not_awaited()

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

    async def test_answer_modal_handles_missing_question_and_already_solved(self):
        interaction = AsyncMock()
        interaction.user.id = 123
        modal = AnswerModal(self.mock_bot, "Question", 123)
        modal.answer_input._value = "answer"
        self.mock_bot.game.daily_q = None

        await modal.on_submit(interaction)

        self.assertIn("no active question", interaction.followup.send.call_args.args[0])

        self.mock_bot.game.daily_q = MagicMock(answer="Answer")
        self.mock_bot.game.handle_guess.side_effect = AlreadyAnsweredCorrectlyError()
        interaction = AsyncMock()
        interaction.user.id = 123
        modal = AnswerModal(self.mock_bot, "Question", 123)
        modal.answer_input._value = "answer"

        await modal.on_submit(interaction)

        interaction.followup.send.assert_awaited_once_with(
            "You already solved today.", ephemeral=True
        )

    async def test_answer_modal_handles_jinxed_and_unexpected_failures(self):
        self.mock_bot.game.daily_q = MagicMock(answer="Answer")
        self.mock_bot.game.daily_question_id = 42
        self.mock_bot.game.handle_guess.side_effect = JinxedError("silenced")
        interaction = AsyncMock()
        interaction.user.id = 123
        modal = AnswerModal(self.mock_bot, "Question", 123)
        modal.answer_input._value = "answer"

        with unittest.mock.patch("src.cogs.quick_actions.ConfigReader") as config:
            config.return_value.get.return_value = "🤐"
            await modal.on_submit(interaction)

        self.assertIn("silenced", interaction.followup.send.call_args.args[0])

        self.mock_bot.game.handle_guess.side_effect = RuntimeError("write failed")
        interaction = AsyncMock()
        interaction.user.id = 123
        modal = AnswerModal(self.mock_bot, "Question", 123)
        modal.answer_input._value = "answer"

        await modal.on_submit(interaction)

        self.assertIn("error occurred", interaction.followup.send.call_args.args[0])

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


class TestQuickActionPowerupCallbacks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database(":memory:")
        self.data_manager = DataManager(self.db)
        self.player_manager = PlayerManager(self.data_manager)
        self.player_manager.get_or_create_player("attacker", "Attacker")
        self.player_manager.get_or_create_player("target", "Target")
        self.player_manager.set_streak("attacker", 8)
        self.question = Question("Question", "Answer", "Test", 100)
        self.daily_question_id = self.data_manager.log_daily_question(self.question)
        _, _, question_db_id = self.data_manager.get_todays_daily_question()
        self.config = make_config()
        self.powerups = PowerUpManager(
            self.player_manager, self.data_manager, self.config
        )

        self.bot = MagicMock()
        self.bot.game.daily_q = self.question
        self.bot.game.daily_question_id = self.daily_question_id
        self.bot.game.question_db_id = question_db_id
        self.bot.game.data_manager = self.data_manager
        self.bot.game.player_manager = self.player_manager
        self.bot.game.managers = {"powerup": self.powerups}
        self.bot.game.season_manager.enabled = False

        self.config_patcher = unittest.mock.patch(
            "src.cogs.quick_actions.ConfigReader", return_value=self.config
        )
        self.config_patcher.start()
        self.addCleanup(self.config_patcher.stop)

    async def asyncTearDown(self):
        self.db.close()

    @staticmethod
    def make_interaction(user_id="attacker"):
        interaction = AsyncMock()
        interaction.user.id = user_id
        interaction.user.display_name = str(user_id)
        interaction.user.mention = f"<@{user_id}>"
        interaction.channel.send = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()
        interaction.edit_original_response = AsyncMock()
        return interaction

    async def test_jinx_select_runs_real_forward_jinx(self):
        view = JinxSelectView(self.bot, "attacker")
        select = next(
            child
            for child in view.children
            if getattr(child, "custom_id", None) == "jinx_string_select"
        )
        self.assertIn("target", [option.value for option in select.options])
        select._values = ["target"]
        interaction = self.make_interaction()

        await select.callback(interaction)

        self.assertEqual(self.powerups.daily_state["target"].jinxed_by, "attacker")
        interaction.edit_original_response.assert_awaited_once()
        self.assertEqual(
            self.data_manager.get_powerup_usages_for_question(self.daily_question_id)[
                0
            ]["powerup_type"],
            "jinx",
        )

    async def test_jinx_select_publishes_retroactive_result(self):
        handler = GuessHandler(
            self.data_manager,
            self.player_manager,
            self.question,
            self.daily_question_id,
            {"powerup": self.powerups},
            config=self.config,
            question_db_id=self.bot.game.question_db_id,
        )
        handler.handle_guess("target", "Target", "Answer")
        view = JinxSelectView(self.bot, "attacker")
        select = next(
            child
            for child in view.children
            if getattr(child, "custom_id", None) == "jinx_string_select"
        )
        select._values = ["target"]
        interaction = self.make_interaction()

        await select.callback(interaction)

        interaction.channel.send.assert_awaited_once()
        interaction.edit_original_response.assert_awaited_once_with(
            content="✅ Done.", view=None
        )

    async def test_steal_select_runs_real_forward_steal(self):
        view = StealSelectView(self.bot, "attacker")
        select = next(
            child
            for child in view.children
            if getattr(child, "custom_id", None) == "steal_string_select"
        )
        self.assertIn("target", [option.value for option in select.options])
        select._values = ["target"]
        interaction = self.make_interaction()

        await select.callback(interaction)

        self.assertEqual(
            self.powerups.daily_state["target"].steal_attempt_by, "attacker"
        )
        interaction.edit_original_response.assert_awaited_once()
        self.assertEqual(
            self.data_manager.get_powerup_usages_for_question(self.daily_question_id)[
                0
            ]["powerup_type"],
            "steal",
        )

    async def test_steal_select_publishes_retroactive_result(self):
        handler = GuessHandler(
            self.data_manager,
            self.player_manager,
            self.question,
            self.daily_question_id,
            {"powerup": self.powerups},
            config=self.config,
            question_db_id=self.bot.game.question_db_id,
        )
        handler.handle_guess("target", "Target", "Answer")
        view = StealSelectView(self.bot, "attacker")
        select = next(
            child
            for child in view.children
            if getattr(child, "custom_id", None) == "steal_string_select"
        )
        select._values = ["target"]
        interaction = self.make_interaction()

        await select.callback(interaction)

        interaction.channel.send.assert_awaited_once()
        interaction.edit_original_response.assert_awaited_once_with(
            content="✅ Done.", view=None
        )

    async def test_jinx_select_rejects_empty_selection(self):
        view = JinxSelectView(self.bot, "attacker")
        select = next(
            child
            for child in view.children
            if getattr(child, "custom_id", None) == "jinx_string_select"
        )
        interaction = self.make_interaction()

        await select.callback(interaction)

        interaction.followup.send.assert_awaited_once_with(
            "No player selected.", ephemeral=True
        )

    async def test_jinx_select_handles_missing_manager_and_powerup_error(self):
        self.bot.game.managers = {}
        view = JinxSelectView(self.bot, "attacker")
        select = next(
            child
            for child in view.children
            if getattr(child, "custom_id", None) == "jinx_string_select"
        )
        select._values = ["target"]
        interaction = self.make_interaction()

        await select.callback(interaction)

        self.assertIn("not available", interaction.followup.send.call_args.args[0])

        manager = MagicMock()
        manager.get_valid_jinx_targets.return_value = [("target", "Target")]
        manager.daily_state = {}
        manager.jinx.side_effect = PowerUpError("target is unavailable")
        self.bot.game.managers = {"powerup": manager}
        view = JinxSelectView(self.bot, "attacker")
        select = next(
            child
            for child in view.children
            if getattr(child, "custom_id", None) == "jinx_string_select"
        )
        select._values = ["target"]
        interaction = self.make_interaction()

        await select.callback(interaction)

        interaction.followup.send.assert_awaited_once_with(
            "target is unavailable", ephemeral=True
        )

    async def test_rest_confirmation_handles_no_question(self):
        self.bot.game.daily_q = None
        view = RestConfirmationView(self.bot)
        button = next(
            child
            for child in view.children
            if getattr(child, "custom_id", None) == "rest_confirm"
        )
        interaction = self.make_interaction()

        await button.callback(interaction)

        interaction.followup.send.assert_awaited_once_with(
            "There is no active question right now.", ephemeral=True
        )

    async def test_rest_confirmation_handles_missing_manager(self):
        self.bot.game.managers = {}
        view = RestConfirmationView(self.bot)
        button = next(
            child
            for child in view.children
            if getattr(child, "custom_id", None) == "rest_confirm"
        )
        interaction = self.make_interaction()

        await button.callback(interaction)

        interaction.followup.send.assert_awaited_once_with(
            "Power-ups are not available.", ephemeral=True
        )

    async def test_rest_confirmation_persists_and_sends_both_messages(self):
        view = RestConfirmationView(self.bot)
        button = next(
            child
            for child in view.children
            if getattr(child, "custom_id", None) == "rest_confirm"
        )
        interaction = self.make_interaction()

        await button.callback(interaction)

        self.assertTrue(self.powerups.daily_state["attacker"].is_resting)
        self.assertEqual(self.data_manager.get_pending_multiplier("attacker"), 0.2)
        self.assertEqual(
            self.data_manager.get_powerup_usages_for_question(self.daily_question_id)[
                0
            ]["powerup_type"],
            "rest",
        )
        interaction.channel.send.assert_awaited_once()
        interaction.followup.send.assert_awaited_once()


class TestQuickActionAdminModals(unittest.IsolatedAsyncioTestCase):
    async def test_add_answer_modal_previews_before_apply(self):
        bot = MagicMock()
        bot.game.season_manager.enabled = False
        bot.game.recalculate_scores_for_new_answer.return_value = {
            "status": "success",
            "updated_players": 1,
            "total_refunded": 140,
            "age_warning": "",
            "details": [],
            "rest_cleared_players": [],
        }
        modal = AddAnswerModal(bot)
        modal.answer_input._value = "  Accepted spelling  "
        interaction = AsyncMock()
        interaction.user.id = 42

        await modal.on_submit(interaction)

        bot.game.recalculate_scores_for_new_answer.assert_called_once_with(
            "Accepted spelling", "42", dry_run=True
        )
        preview = interaction.followup.send.call_args.args[0]
        self.assertIn("DRY RUN PREVIEW", preview)
        self.assertIn("Accepted spelling", preview)
        self.assertIsInstance(
            interaction.followup.send.call_args.kwargs["view"],
            AddAnswerConfirmationView,
        )

    async def test_refund_modal_persists_score_streak_and_adjustment(self):
        db = Database(":memory:")
        try:
            data_manager = DataManager(db)
            player_manager = PlayerManager(data_manager)
            player_manager.get_or_create_player("admin", "Admin")
            player_manager.get_or_create_player("player", "Player")
            player_manager.update_score("player", 100)
            player_manager.set_streak("player", 2)

            bot = MagicMock()
            bot.player_manager = player_manager
            bot.data_manager = data_manager
            member = MagicMock(id="player", display_name="Player", mention="<@player>")
            modal = RefundModal(bot, member)
            modal.amount_input._value = "25"
            modal.streak_input._value = "4"
            modal.reason_input._value = "Correction"
            interaction = AsyncMock()
            interaction.user.id = "admin"

            await modal.on_submit(interaction)

            player = player_manager.get_player("player")
            self.assertEqual((player.score, player.answer_streak), (125, 4))
            adjustment = db.execute_query(
                "SELECT amount, reason FROM score_adjustments WHERE player_id = ?",
                ("player",),
            )[0]
            self.assertEqual(
                (adjustment["amount"], adjustment["reason"]), (25, "Correction")
            )
            interaction.channel.send.assert_awaited_once()
            interaction.followup.send.assert_awaited_once_with(
                "Refund processed.", ephemeral=True
            )
        finally:
            db.close()

    async def test_refund_modal_rejects_invalid_amount_and_streak(self):
        bot = MagicMock()
        modal = RefundModal(bot, MagicMock(id="player", display_name="Player"))
        modal.amount_input._value = "not a number"
        modal.streak_input._value = ""
        modal.reason_input._value = "Correction"
        interaction = AsyncMock()

        await modal.on_submit(interaction)

        self.assertIn("Amount must be", interaction.followup.send.call_args.args[0])
        bot.player_manager.get_or_create_player.assert_not_called()

        modal.amount_input._value = "25"
        modal.streak_input._value = "not a streak"
        interaction = AsyncMock()

        await modal.on_submit(interaction)

        self.assertIn("Streak must be", interaction.followup.send.call_args.args[0])
        bot.player_manager.get_or_create_player.assert_not_called()


class TestQuickActionConfirmationCallbacks(unittest.IsolatedAsyncioTestCase):
    async def test_skip_confirmation_reports_success_and_failure(self):
        bot = MagicMock()
        bot.game.daily_q = Question("Question", "Answer", "Test", 100)
        bot.game.format_question.return_value = "New question"
        view = SkipConfirmationView(bot)
        button = next(
            child
            for child in view.children
            if getattr(child, "custom_id", None) == "admin:skip_confirm"
        )

        success_interaction = AsyncMock()
        bot.game.reset_daily_question.return_value = True
        await button.callback(success_interaction)
        success_interaction.channel.send.assert_awaited_once()
        self.assertIn(
            "New question", success_interaction.channel.send.call_args.args[0]
        )

        failure_interaction = AsyncMock()
        bot.game.reset_daily_question.return_value = False
        await button.callback(failure_interaction)
        self.assertIn(
            "Failed to skip", failure_interaction.followup.send.call_args.args[0]
        )

    async def test_add_answer_confirmation_applies_and_syncs_state(self):
        bot = MagicMock()
        bot.morning_message_task.is_running.return_value = True
        bot.evening_message_task.is_running.return_value = True
        bot.morning_message_task.next_iteration = 1
        bot.evening_message_task.next_iteration = 2
        bot.game.season_manager.enabled = False
        bot.game.managers = {"powerup": MagicMock(daily_state={})}
        state = MagicMock()
        state.is_correct = True
        bot.game.recalculate_scores_for_new_answer.return_value = {
            "status": "success",
            "updated_players": 1,
            "total_refunded": 100,
            "age_warning": "",
            "details": [
                {
                    "user_id": "target",
                    "score_before": 0,
                    "score_after": 140,
                    "season_score_before": 0,
                    "season_score_after": 140,
                    "diff": 140,
                    "badges": ["🎯"],
                }
            ],
            "rest_cleared_players": [{"user_id": "target"}],
            "daily_state_new": {"target": state},
        }
        view = AddAnswerConfirmationView(bot, "Accepted", "admin")
        button = next(
            child
            for child in view.children
            if getattr(child, "custom_id", None) == "admin:add_answer_apply"
        )
        interaction = AsyncMock()

        await button.callback(interaction)

        bot.game.recalculate_scores_for_new_answer.assert_called_once_with(
            "Accepted", "admin", dry_run=False
        )
        self.assertIs(bot.game.managers["powerup"].daily_state["target"], state)
        public_message = interaction.channel.send.call_args.args[0]
        self.assertIn("||Accepted||", public_message)
        self.assertIn("<@target>: 0 -> 140 (+140)", public_message)
        self.assertIn("Rest revoked", public_message)
        interaction.channel.send.assert_awaited_once()
        interaction.followup.send.assert_awaited_once_with(
            "✅ Answer applied and scores updated.", ephemeral=True
        )

    async def test_add_answer_cancel_does_not_apply(self):
        bot = MagicMock()
        view = AddAnswerConfirmationView(bot, "Accepted", "admin")
        button = next(
            child
            for child in view.children
            if getattr(child, "custom_id", None) == "admin:add_answer_cancel"
        )
        interaction = AsyncMock()

        await button.callback(interaction)

        bot.game.recalculate_scores_for_new_answer.assert_not_called()
        interaction.followup.send.assert_awaited_once_with("Cancelled.", ephemeral=True)

    async def test_add_answer_modal_reports_recalculation_error(self):
        bot = MagicMock()
        bot.game.recalculate_scores_for_new_answer.return_value = {
            "status": "error",
            "message": "No active question",
        }
        modal = AddAnswerModal(bot)
        modal.answer_input._value = "Accepted"
        interaction = AsyncMock()
        interaction.user.id = 42

        await modal.on_submit(interaction)

        interaction.followup.send.assert_awaited_once_with(
            "❌ Error: No active question", ephemeral=True
        )

    async def test_refund_select_requires_target_then_opens_modal(self):
        bot = MagicMock()
        view = RefundSelectView(bot)
        select = view.children[0]
        interaction = AsyncMock()
        select._values = []

        await select.callback(interaction)

        interaction.followup.send.assert_awaited_once_with(
            "No player selected.", ephemeral=True
        )

        interaction = AsyncMock()
        member = MagicMock(id=42, display_name="Player")
        select._values = [member]

        await select.callback(interaction)

        self.assertIsInstance(
            interaction.followup.send_modal.call_args.args[0], RefundModal
        )


if __name__ == "__main__":
    unittest.main()
