import unittest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from data.readers.question import Question
from src.cogs.quick_actions import (
    AddAnswerModal,
    AddAnswerConfirmationView,
    AdminMenuView,
    AnswerModal,
    GameActionView,
    JinxSelectView,
    RefundModal,
    RefundSelectView,
    RestConfirmationView,
    SkipConfirmationView,
    StealSelectView,
)
from tests.src.cogs._game_stack import build_game_stack


def make_interaction(user_id, name=None):
    interaction = AsyncMock()
    interaction.user.id = user_id
    interaction.user.display_name = name or str(user_id)
    interaction.user.mention = f"<@{user_id}>"
    return interaction


def find_child(view, custom_id):
    return next(
        child
        for child in view.children
        if getattr(child, "custom_id", None) == custom_id
    )


class QuickActionTestCase(unittest.IsolatedAsyncioTestCase):
    """Builds a real game stack and a bot double wrapping it."""

    players = (("123", "Player"), ("456", "Target"))
    question = None

    def setUp(self):
        self.stack = build_game_stack(
            self, players=self.players, question=self.question
        )
        self._use_stack(self.stack)
        # ConfigReader is an external boundary (reads .env).
        for target in (
            "src.cogs.quick_actions.ConfigReader",
            "src.cfg.main.ConfigReader",
        ):
            patcher = patch(target, return_value=self.stack.config)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _use_stack(self, stack):
        self.stack = stack
        self.game = stack.game
        self.data_manager = stack.data_manager
        self.player_manager = stack.player_manager
        self.powerups = stack.game.managers["powerup"]
        # The Discord bot and its scheduler tasks are the external boundary.
        self.bot = MagicMock()
        self.bot.game = self.game
        self.bot.player_manager = self.player_manager
        self.bot.data_manager = self.data_manager
        self.bot.morning_message_task.is_running.return_value = False
        self.bot.evening_message_task.is_running.return_value = False

    def _set_revealed(self):
        now = datetime.now()
        self.bot.morning_message_task.is_running.return_value = True
        self.bot.evening_message_task.is_running.return_value = True
        self.bot.morning_message_task.next_iteration = now + timedelta(hours=1)
        self.bot.evening_message_task.next_iteration = now + timedelta(hours=12)

    def _log_wrong_guesses(self, player_id, texts, name="Player"):
        for text in texts:
            self.data_manager.log_player_guess(
                str(player_id), name, self.game.daily_question_id, text, False
            )

    def _usages(self):
        return [
            (row["user_id"], row["powerup_type"], row["target_user_id"])
            for row in self.data_manager.get_powerup_usages_for_question(
                self.game.daily_question_id
            )
        ]

    def _alternative_answers(self):
        return self.data_manager.get_alternative_answers(self.game.question_db_id)


class TestGameActionView(QuickActionTestCase):
    """Tests for the GameActionView main button view and answer modal."""

    def _button(self, custom_id, view=None):
        return find_child(view or GameActionView(self.bot), custom_id)

    async def test_answer_button_no_question(self):
        """Test answer button when no question is active."""
        self._use_stack(build_game_stack(self, start_day=False))
        interaction = make_interaction(123)

        await self._button("trivia:answer").callback(interaction)

        interaction.response.send_message.assert_called_once_with(
            "There is no active question.", ephemeral=True
        )
        interaction.response.send_modal.assert_not_called()

    async def test_answer_button_with_question(self):
        """Test answer button opens modal with question displayed."""
        interaction = make_interaction(123)

        await self._button("trivia:answer").callback(interaction)

        modal = interaction.response.send_modal.call_args.args[0]
        self.assertIsInstance(modal, AnswerModal)
        self.assertEqual(modal.question_text, "What is 2 + 2?")
        interaction.response.send_message.assert_not_called()

    async def test_answer_button_blocks_player_when_manager_denies_answer(self):
        self.powerups.jinx("123", "456", self.game.daily_question_id)
        interaction = make_interaction(123)

        await self._button("trivia:answer").callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        self.assertIn(
            "You are Jinxed!", interaction.response.send_message.call_args.args[0]
        )
        interaction.response.send_modal.assert_not_awaited()

    async def test_answer_button_limits_previous_guesses_placeholder(self):
        self._log_wrong_guesses(123, [f"wrong guess {i}" for i in range(20)])
        interaction = make_interaction(123)

        await self._button("trivia:answer").callback(interaction)

        modal = interaction.response.send_modal.call_args.args[0]
        self.assertIsInstance(modal, AnswerModal)
        self.assertLessEqual(len(modal.answer_input.placeholder), 100)
        self.assertIn("(truncated)", modal.answer_input.placeholder)
        self.assertIn("wrong guess 0", modal.answer_input.placeholder)

    async def test_answer_modal_placeholder_boundary_and_long_single_guess(self):
        prefix = "Your previous guesses:\n1. "
        for player_id, guess_length in ((301, 100 - len(prefix)), (302, 500)):
            with self.subTest(guess_length=guess_length):
                self._log_wrong_guesses(player_id, ["x" * guess_length])
                modal = AnswerModal(self.bot, "Question", player_id)
                placeholder = modal.answer_input.placeholder
                self.assertLessEqual(len(placeholder), 100)
                self.assertEqual("(truncated)" in placeholder, guess_length == 500)

    async def test_answer_modal_without_history_shows_default_placeholder(self):
        modal = AnswerModal(self.bot, "Question", 123)
        self.assertEqual(modal.answer_input.placeholder, "Type your answer here...")

    async def test_answer_modal_long_history_still_sends_feedback_and_announcement(
        self,
    ):
        for user_id, guess, is_correct in ((201, "nope", False), (202, "4", True)):
            with self.subTest(is_correct=is_correct):
                self._log_wrong_guesses(
                    user_id, [f"guess {i:03d} " + "x" * 100 for i in range(30)]
                )
                interaction = make_interaction(user_id, "Player")
                modal = AnswerModal(self.bot, "Question", user_id)
                modal.answer_input._value = guess

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
        empty = build_game_stack(self, start_day=False)
        interaction = make_interaction(123)
        modal = AnswerModal(MagicMock(game=empty.game), "Question", 123)
        modal.answer_input._value = "answer"

        await modal.on_submit(interaction)

        self.assertIn("no active question", interaction.followup.send.call_args.args[0])

        for _ in range(2):
            interaction = make_interaction(123)
            modal = AnswerModal(self.bot, "Question", 123)
            modal.answer_input._value = "4"
            await modal.on_submit(interaction)

        interaction.followup.send.assert_awaited_once_with(
            "You already solved today.", ephemeral=True
        )
        interaction.channel.send.assert_not_awaited()

    async def test_answer_modal_handles_jinxed_and_unexpected_failures(self):
        self.powerups.jinx("123", "456", self.game.daily_question_id)
        interaction = make_interaction(123)
        modal = AnswerModal(self.bot, "Question", 123)
        modal.answer_input._value = "4"

        await modal.on_submit(interaction)

        self.assertIn("You are Jinxed!", interaction.followup.send.call_args.args[0])
        self.assertFalse(self.player_manager.get_player("123").score)

        interaction = make_interaction(456)
        modal = AnswerModal(self.bot, "Question", 456)
        modal.answer_input._value = "4"

        with patch.object(
            self.game, "handle_guess", side_effect=RuntimeError("write failed")
        ):
            await modal.on_submit(interaction)

        self.assertIn("error occurred", interaction.followup.send.call_args.args[0])

    async def test_jinx_button_shows_selection(self):
        """Test jinx button shows player selection view."""
        interaction = make_interaction(123)

        await self._button("trivia:jinx").callback(interaction)

        interaction.response.send_message.assert_called_once()
        view = interaction.response.send_message.call_args.kwargs["view"]
        self.assertIsInstance(view, JinxSelectView)
        self.assertEqual([option.value for option in view.select.options], ["456"])

    async def test_jinx_button_without_targets_reports_none_available(self):
        self._use_stack(
            build_game_stack(self, players=(("123", "Player"),)),
        )
        interaction = make_interaction(123)

        await self._button("trivia:jinx").callback(interaction)

        self.assertIn(
            "No eligible targets",
            interaction.response.send_message.call_args.args[0],
        )

    async def test_steal_button_shows_selection(self):
        """Test steal button shows player selection view."""
        interaction = make_interaction(123)

        await self._button("trivia:steal").callback(interaction)

        interaction.response.send_message.assert_called_once()
        view = interaction.response.send_message.call_args.kwargs["view"]
        self.assertIsInstance(view, StealSelectView)
        self.assertEqual([option.value for option in view.select.options], ["456"])

    async def test_attack_buttons_block_after_attack_used(self):
        self.powerups.jinx("123", "456", self.game.daily_question_id)
        for custom_id in ("trivia:jinx", "trivia:steal"):
            with self.subTest(custom_id=custom_id):
                interaction = make_interaction(123)

                await self._button(custom_id).callback(interaction)

                interaction.response.send_message.assert_called_once_with(
                    "You have already used an attack power-up today.", ephemeral=True
                )

    async def test_rest_button_shows_confirmation(self):
        """Test rest button shows confirmation view."""
        interaction = make_interaction(123)

        await self._button("trivia:rest").callback(interaction)

        interaction.response.send_message.assert_called_once()
        self.assertIsInstance(
            interaction.response.send_message.call_args.kwargs["view"],
            RestConfirmationView,
        )

    async def test_rest_button_blocks_player_who_already_answered(self):
        self.game.handle_guess(123, "Player", "4")
        interaction = make_interaction(123)

        await self._button("trivia:rest").callback(interaction)

        interaction.response.send_message.assert_called_once()
        self.assertIn(
            "cannot rest", interaction.response.send_message.call_args.args[0]
        )

    async def test_admin_button_permission_denied(self):
        """Test admin button denies access to non-admins."""
        interaction = AsyncMock()
        interaction.user.guild_permissions.administrator = False

        await self._button("trivia:admin").callback(interaction)

        interaction.response.send_message.assert_called_once_with(
            "You don't have permission to access admin functions.", ephemeral=True
        )

    async def test_admin_button_shows_menu(self):
        """Test admin button shows admin menu for admins."""
        interaction = AsyncMock()
        interaction.user.guild_permissions.administrator = True

        await self._button("trivia:admin").callback(interaction)

        interaction.response.send_message.assert_called_once()
        self.assertIsInstance(
            interaction.response.send_message.call_args.kwargs["view"], AdminMenuView
        )

    async def test_view_persistent(self):
        """Test that GameActionView has no timeout for persistence."""
        view = GameActionView(self.bot)
        self.assertIsNone(view.timeout)

    async def test_view_has_all_buttons(self):
        """Test that GameActionView has all expected buttons."""
        view = GameActionView(self.bot)
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


class TestQuickActionPowerupCallbacks(QuickActionTestCase):
    players = (("attacker", "Attacker", 8), ("target", "Target"))
    question = Question("Question", "Answer", "Test", 100)

    def _select(self, view_class, custom_id, *values):
        select = find_child(view_class(self.bot, "attacker"), custom_id)
        select._values = list(values)
        return select

    def _jinx_select(self, *values):
        return self._select(JinxSelectView, "jinx_string_select", *values)

    def _steal_select(self, *values):
        return self._select(StealSelectView, "steal_string_select", *values)

    async def test_jinx_select_runs_real_forward_jinx(self):
        view = JinxSelectView(self.bot, "attacker")
        select = find_child(view, "jinx_string_select")
        self.assertIn("target", [option.value for option in select.options])
        select._values = ["target"]
        interaction = make_interaction("attacker")

        await select.callback(interaction)

        self.assertEqual(self.powerups.daily_state["target"].jinxed_by, "attacker")
        interaction.edit_original_response.assert_awaited_once()
        self.assertEqual(self._usages(), [("attacker", "jinx", "target")])

    async def test_jinx_select_publishes_retroactive_result(self):
        self.game.handle_guess("target", "Target", "Answer")
        target_score = self.player_manager.get_player("target").score
        interaction = make_interaction("attacker")

        await self._jinx_select("target").callback(interaction)

        interaction.channel.send.assert_awaited_once()
        interaction.edit_original_response.assert_awaited_once_with(
            content="✅ Done.", view=None
        )
        self.assertGreater(self.player_manager.get_player("attacker").score, 0)
        self.assertLess(self.player_manager.get_player("target").score, target_score)

    async def test_steal_select_runs_real_forward_steal(self):
        view = StealSelectView(self.bot, "attacker")
        select = find_child(view, "steal_string_select")
        self.assertIn("target", [option.value for option in select.options])
        select._values = ["target"]
        interaction = make_interaction("attacker")

        await select.callback(interaction)

        self.assertEqual(
            self.powerups.daily_state["target"].steal_attempt_by, "attacker"
        )
        interaction.edit_original_response.assert_awaited_once()
        self.assertEqual(self._usages(), [("attacker", "steal", "target")])

    async def test_steal_select_publishes_retroactive_result(self):
        self.game.handle_guess("target", "Target", "Answer")
        target_score = self.player_manager.get_player("target").score
        interaction = make_interaction("attacker")

        await self._steal_select("target").callback(interaction)

        interaction.channel.send.assert_awaited_once()
        interaction.edit_original_response.assert_awaited_once_with(
            content="✅ Done.", view=None
        )
        self.assertGreater(self.player_manager.get_player("attacker").score, 0)
        self.assertLess(self.player_manager.get_player("target").score, target_score)
        self.assertLess(self.player_manager.get_player("attacker").answer_streak, 8)

    async def test_jinx_select_rejects_empty_selection(self):
        interaction = make_interaction("attacker")

        await self._jinx_select().callback(interaction)

        interaction.followup.send.assert_awaited_once_with(
            "No player selected.", ephemeral=True
        )
        self.assertEqual(self._usages(), [])

    async def test_jinx_select_handles_missing_manager_and_powerup_error(self):
        select = self._jinx_select("target")
        # GameRunner always registers a powerup manager; emptying the registry
        # exercises the defensive branch.
        with patch.dict(self.game.managers, {}, clear=True):
            interaction = make_interaction("attacker")
            await select.callback(interaction)

        self.assertIn("not available", interaction.followup.send.call_args.args[0])
        self.assertEqual(self._usages(), [])

        await self._jinx_select("target").callback(make_interaction("attacker"))
        interaction = make_interaction("attacker")

        await self._jinx_select("target").callback(interaction)

        interaction.followup.send.assert_awaited_once_with(
            "You have already used an attack power-up today.", ephemeral=True
        )
        self.assertEqual(self._usages(), [("attacker", "jinx", "target")])

    async def test_rest_confirmation_handles_no_question(self):
        self._use_stack(build_game_stack(self, start_day=False))
        button = find_child(RestConfirmationView(self.bot), "rest_confirm")
        interaction = make_interaction("attacker")

        await button.callback(interaction)

        interaction.followup.send.assert_awaited_once_with(
            "There is no active question right now.", ephemeral=True
        )

    async def test_rest_confirmation_handles_missing_manager(self):
        button = find_child(RestConfirmationView(self.bot), "rest_confirm")
        interaction = make_interaction("attacker")

        # GameRunner always registers a powerup manager; emptying the registry
        # exercises the defensive branch.
        with patch.dict(self.game.managers, {}, clear=True):
            await button.callback(interaction)

        interaction.followup.send.assert_awaited_once_with(
            "Power-ups are not available.", ephemeral=True
        )
        self.assertEqual(self._usages(), [])

    async def test_rest_confirmation_persists_and_sends_both_messages(self):
        button = find_child(RestConfirmationView(self.bot), "rest_confirm")
        interaction = make_interaction("attacker")

        await button.callback(interaction)

        self.assertTrue(self.powerups.daily_state["attacker"].is_resting)
        self.assertEqual(self.data_manager.get_pending_multiplier("attacker"), 0.2)
        self.assertEqual(self._usages(), [("attacker", "rest", None)])
        interaction.channel.send.assert_awaited_once()
        interaction.followup.send.assert_awaited_once()

    async def test_rest_initializes_season_score(self):
        season_id = self.data_manager.create_season(
            "Test Season", date.today().isoformat(), date.today().isoformat()
        )
        button = find_child(RestConfirmationView(self.bot), "rest_confirm")
        interaction = make_interaction("attacker")

        await button.callback(interaction)

        season_score = self.data_manager.get_player_season_score("attacker", season_id)
        self.assertIsNotNone(season_score)
        self.assertEqual(season_score.points, 0)


class TestQuickActionAdminModals(QuickActionTestCase):
    players = (("111", "Player1"), ("222", "Player2"), ("admin", "Admin"))

    async def test_add_answer_modal_previews_before_apply(self):
        self.game.handle_guess(111, "Player1", "Accepted spelling")
        modal = AddAnswerModal(self.bot)
        modal.answer_input._value = "  Accepted spelling  "
        interaction = make_interaction(42)

        await modal.on_submit(interaction)

        preview = interaction.followup.send.call_args.args[0]
        self.assertIn("[DRY RUN]", preview)
        self.assertIn("apply=True", preview)
        self.assertIn("Would update 1 players.", preview)
        self.assertNotIn("Accepted spelling", preview)
        self.assertIsInstance(
            interaction.followup.send.call_args.kwargs["view"],
            AddAnswerConfirmationView,
        )
        self.assertEqual(self._alternative_answers(), [])
        self.assertEqual(self.player_manager.get_player("111").score, 0)

    async def test_refund_modal_persists_score_streak_and_adjustment(self):
        self.player_manager.update_score("111", 100)
        self.player_manager.set_streak("111", 2)
        member = MagicMock(id="111", display_name="Player1", mention="<@111>")
        modal = RefundModal(self.bot, member)
        modal.amount_input._value = "25"
        modal.streak_input._value = "4"
        modal.reason_input._value = "Correction"
        interaction = make_interaction("admin")

        await modal.on_submit(interaction)

        player = self.player_manager.get_player("111")
        self.assertEqual((player.score, player.answer_streak), (125, 4))
        adjustment = self.stack.db.execute_query(
            "SELECT amount, reason FROM score_adjustments WHERE player_id = ?",
            ("111",),
        )[0]
        self.assertEqual(
            (adjustment["amount"], adjustment["reason"]), (25, "Correction")
        )
        interaction.channel.send.assert_awaited_once()
        interaction.followup.send.assert_awaited_once_with(
            "Refund processed.", ephemeral=True
        )

    async def test_refund_modal_rejects_invalid_amount_and_streak(self):
        member = MagicMock(id="333", display_name="Newcomer")
        modal = RefundModal(self.bot, member)
        modal.amount_input._value = "not a number"
        modal.streak_input._value = ""
        modal.reason_input._value = "Correction"
        interaction = AsyncMock()

        await modal.on_submit(interaction)

        self.assertIn("Amount must be", interaction.followup.send.call_args.args[0])

        modal.amount_input._value = "25"
        modal.streak_input._value = "not a streak"
        interaction = AsyncMock()

        await modal.on_submit(interaction)

        self.assertIn("Streak must be", interaction.followup.send.call_args.args[0])
        self.assertIsNone(self.player_manager.get_player("333"))
        self.assertEqual(
            self.stack.db.execute_query("SELECT * FROM score_adjustments"), []
        )


class TestQuickActionConfirmationCallbacks(QuickActionTestCase):
    players = (("111", "Player1"), ("222", "Player2"), ("999", "Sleepy"))

    async def test_skip_confirmation_reports_success_and_failure(self):
        original_id = self.game.daily_question_id
        view = SkipConfirmationView(self.bot)
        button = find_child(view, "admin:skip_confirm")

        self.stack.question_selector.get_random_question.return_value = Question(
            "Replacement question?", "Replacement", "Misc", 100
        )
        success_interaction = AsyncMock()
        await button.callback(success_interaction)

        success_interaction.channel.send.assert_awaited_once()
        self.assertIn(
            "Replacement question?", success_interaction.channel.send.call_args.args[0]
        )
        self.assertEqual(self.game.daily_q.question, "Replacement question?")
        self.assertNotEqual(self.game.daily_question_id, original_id)

        replacement_id = self.game.daily_question_id
        self.stack.question_selector.get_random_question.return_value = None
        failure_interaction = AsyncMock()
        await button.callback(failure_interaction)

        self.assertIn(
            "Failed to skip", failure_interaction.followup.send.call_args.args[0]
        )
        self.assertEqual(self.game.daily_question_id, replacement_id)
        self.assertEqual(self.game.daily_q.question, "Replacement question?")

    async def test_add_answer_confirmation_applies_and_syncs_state(self):
        self._set_revealed()
        self.game.handle_guess(111, "Player1", "Accepted")
        self.data_manager.log_powerup_usage(
            "999", "rest", None, self.game.daily_question_id
        )
        self.data_manager.log_player_guess(
            "999", "Sleepy", self.game.daily_question_id, "Accepted", False
        )
        view = AddAnswerConfirmationView(self.bot, "Accepted", "admin")
        button = find_child(view, "admin:add_answer_apply")
        interaction = AsyncMock()

        await button.callback(interaction)

        self.assertEqual(self._alternative_answers(), ["Accepted"])
        score = self.player_manager.get_player("111").score
        self.assertGreater(score, 0)
        self.assertTrue(self.powerups.daily_state["111"].is_correct)
        public_message = interaction.channel.send.call_args.args[0]
        self.assertIn("||Accepted||", public_message)
        self.assertIn(f"<@111>: 0 -> {score} (+{score})", public_message)
        self.assertIn("Rest revoked", public_message)
        self.assertIn("<@999>", public_message)
        interaction.channel.send.assert_awaited_once()
        interaction.followup.send.assert_awaited_once_with(
            "✅ Answer applied and scores updated.", ephemeral=True
        )

    async def test_add_answer_cancel_does_not_apply(self):
        self.game.handle_guess(111, "Player1", "Accepted")
        view = AddAnswerConfirmationView(self.bot, "Accepted", "admin")
        button = find_child(view, "admin:add_answer_cancel")
        interaction = AsyncMock()

        await button.callback(interaction)

        interaction.followup.send.assert_awaited_once_with("Cancelled.", ephemeral=True)
        self.assertEqual(self._alternative_answers(), [])
        self.assertEqual(self.player_manager.get_player("111").score, 0)

    async def test_add_answer_modal_reports_recalculation_error(self):
        self._use_stack(build_game_stack(self, start_day=False))
        modal = AddAnswerModal(self.bot)
        modal.answer_input._value = "Accepted"
        interaction = make_interaction(42)

        await modal.on_submit(interaction)

        interaction.followup.send.assert_awaited_once_with(
            "❌ Error: No daily question found.", ephemeral=True
        )

    async def test_refund_select_requires_target_then_opens_modal(self):
        view = RefundSelectView(self.bot)
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
