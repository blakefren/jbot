"""Parity contracts for slash-command and Quick Action workflows."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from data.readers.question import Question
from db.database import Database
from src.cogs.admin import Admin
from src.cogs.power import Power
from src.cogs.quick_actions import (
    AddAnswerConfirmationView,
    AddAnswerModal,
    AnswerModal,
    JinxSelectView,
    RefundModal,
    RestConfirmationView,
    SkipConfirmationView,
    StealSelectView,
)
from src.cogs.trivia import Trivia
from src.core.data_manager import DataManager
from src.core.game_runner import GameRunner
from src.core.player_manager import PlayerManager
from src.core.state import DailyPlayerState
from tests.src.core._powerup_helpers import make_config


class TestCommandAndButtonParity(unittest.IsolatedAsyncioTestCase):
    def _make_stack(self):
        db = Database(":memory:")
        data_manager = DataManager(db)
        player_manager = PlayerManager(data_manager)

        for player_id, name in (
            ("100", "Admin"),
            ("101", "Attacker"),
            ("202", "Target"),
        ):
            player_manager.get_or_create_player(player_id, name)
        player_manager.set_streak("101", 8)
        player_manager.set_streak("202", 3)

        question = Question("What is 2 + 2?", "4", "Math", 100)
        daily_question_id = data_manager.log_daily_question(question)
        _, _, question_db_id = data_manager.get_todays_daily_question()
        config = make_config(steal_cost=2, retro_steal_cost=4)
        config.is_seasons_enabled.return_value = False

        with patch("src.core.game_runner.ConfigReader", return_value=config), patch(
            "src.core.powerup.ConfigReader", return_value=config
        ):
            game = GameRunner(MagicMock(), data_manager, player_manager)

        game.daily_q = question
        game.daily_question_id = daily_question_id
        game.question_db_id = question_db_id
        game._build_guess_handler()
        return db, data_manager, player_manager, game

    @staticmethod
    def _interaction(user_id: int):
        interaction = MagicMock()
        interaction.user.id = user_id
        interaction.user.display_name = "Target" if user_id == 202 else "Attacker"
        interaction.user.mention = f"<@{user_id}>"
        interaction.response.defer = AsyncMock()
        interaction.response.send_message = AsyncMock()
        interaction.response.send_modal = AsyncMock()
        interaction.followup.send = AsyncMock()
        interaction.channel.send = AsyncMock()
        interaction.edit_original_response = AsyncMock()
        return interaction

    @staticmethod
    def _game_snapshot(data_manager, player_manager, game):
        players = {
            player_id: (
                player_manager.get_player(player_id).score,
                player_manager.get_player(player_id).season_score,
                player_manager.get_player(player_id).answer_streak,
                player_manager.get_player(player_id).pending_rest_multiplier,
            )
            for player_id in ("100", "101", "202")
        }
        guesses = tuple(
            (row["player_id"], row["guess_text"], row["is_correct"])
            for row in data_manager.get_guesses_for_daily_question(
                game.daily_question_id
            )
        )
        powerups = tuple(
            (
                row["user_id"],
                row["powerup_type"],
                row["target_user_id"],
                row["question_id"],
                row["event_sequence"],
            )
            for row in data_manager.get_powerup_usages_for_question(
                game.daily_question_id
            )
        )
        daily_state = {
            player_id: state
            for player_id, state in game.managers["powerup"]
            .snapshot_transaction_state()
            .items()
            if state != DailyPlayerState()
        }
        alternatives = tuple(data_manager.get_alternative_answers(game.question_db_id))
        adjustments = tuple(
            (row["player_id"], row["amount"], row["reason"])
            for row in data_manager._db.execute_query(
                "SELECT player_id, amount, reason FROM score_adjustments ORDER BY id"
            )
        )
        return players, guesses, powerups, daily_state, alternatives, adjustments

    async def _run_answer(self, use_button: bool, guess: str):
        db, data_manager, player_manager, game = self._make_stack()
        bot = SimpleNamespace(game=game)
        try:
            if use_button:
                interaction = self._interaction(202)
                modal = AnswerModal(bot, game.daily_q.question, 202)
                modal.answer_input._value = guess
                await modal.on_submit(interaction)
                private = [
                    call.args[0] for call in interaction.followup.send.call_args_list
                ]
                public = [
                    call.args[0] for call in interaction.channel.send.call_args_list
                ]
                interaction.response.defer.assert_awaited_once_with(ephemeral=True)
            else:
                cog = Trivia(bot)
                ctx = MagicMock()
                ctx.author.id = 202
                ctx.author.display_name = "Target"
                ctx.author.mention = "<@202>"
                ctx.interaction.response.defer = AsyncMock()
                ctx.interaction.followup.send = AsyncMock()
                ctx.channel.send = AsyncMock()
                await cog.answer.callback(cog, ctx, guess=guess)
                private = [
                    call.args[0]
                    for call in ctx.interaction.followup.send.call_args_list
                ]
                public = [call.args[0] for call in ctx.channel.send.call_args_list]
                ctx.interaction.response.defer.assert_awaited_once_with(ephemeral=True)

            return (
                private,
                public,
                self._game_snapshot(data_manager, player_manager, game),
            )
        finally:
            db.close()

    async def test_answer_slash_and_modal_have_matching_outcomes(self):
        for guess in ("wrong", "4"):
            with self.subTest(guess=guess):
                slash = await self._run_answer(False, guess)
                button = await self._run_answer(True, guess)
                self.assertEqual(button, slash)

    async def _run_power(self, route: str, action: str, target_answered: bool):
        db, data_manager, player_manager, game = self._make_stack()
        if target_answered:
            game.handle_guess(202, "Target", "4")

        bot = SimpleNamespace(game=game, send_message=AsyncMock())
        try:
            if route == "slash":
                cog = Power(bot)
                ctx = MagicMock()
                ctx.author.id = 101
                ctx.interaction = MagicMock()
                if action == "rest":
                    await cog.rest.callback(cog, ctx)
                else:
                    target = SimpleNamespace(id=202)
                    await getattr(cog, action).callback(cog, ctx, target=target)

                messages = [
                    (call.args[0], not call.kwargs.get("ephemeral", False))
                    for call in bot.send_message.await_args_list
                ]
            elif action == "rest":
                view = RestConfirmationView(bot)
                button = next(
                    child
                    for child in view.children
                    if getattr(child, "custom_id", None) == "rest_confirm"
                )
                interaction = self._interaction(101)
                await button.callback(interaction)
                messages = [
                    (interaction.channel.send.call_args.args[0], True),
                    (interaction.followup.send.call_args.args[0], False),
                ]
            else:
                view_type = JinxSelectView if action == "jinx" else StealSelectView
                custom_id = f"{action}_string_select"
                view = view_type(bot, "101")
                select = next(
                    child
                    for child in view.children
                    if getattr(child, "custom_id", None) == custom_id
                )
                self.assertIn("202", [option.value for option in select.options])
                select._values = ["202"]
                interaction = self._interaction(101)
                await select.callback(interaction)
                if interaction.channel.send.await_count:
                    messages = [(interaction.channel.send.call_args.args[0], True)]
                else:
                    messages = [
                        (
                            interaction.edit_original_response.call_args.kwargs[
                                "content"
                            ],
                            False,
                        )
                    ]

            return messages, self._game_snapshot(data_manager, player_manager, game)
        finally:
            db.close()

    async def test_jinx_and_steal_slash_and_button_outcomes_match(self):
        for action in ("jinx", "steal"):
            for target_answered in (False, True):
                with self.subTest(action=action, target_answered=target_answered):
                    slash = await self._run_power("slash", action, target_answered)
                    button = await self._run_power("button", action, target_answered)
                    self.assertEqual(button, slash)

    async def test_rest_slash_and_button_outcomes_match(self):
        slash = await self._run_power("slash", "rest", False)
        button = await self._run_power("button", "rest", False)
        self.assertEqual(button, slash)

    async def _run_refund(self, use_button: bool):
        db, data_manager, player_manager, game = self._make_stack()
        bot = SimpleNamespace(
            game=game, data_manager=data_manager, player_manager=player_manager
        )
        member = SimpleNamespace(id=202, display_name="Target", mention="<@202>")
        try:
            if use_button:
                modal = RefundModal(bot, member)
                modal.amount_input._value = "25"
                modal.streak_input._value = "4"
                modal.reason_input._value = "Correction"
                interaction = self._interaction(100)
                await modal.on_submit(interaction)
                public = interaction.channel.send.call_args.args[0]
            else:
                cog = Admin(bot)
                ctx = MagicMock()
                ctx.author.id = 100
                ctx.send = AsyncMock()
                await cog.refund.callback(cog, ctx, member, 25, 4, reason="Correction")
                public = ctx.send.call_args.args[0]

            return public, self._game_snapshot(data_manager, player_manager, game)
        finally:
            db.close()

    async def test_refund_slash_and_modal_have_matching_persistence(self):
        slash_message, slash_state = await self._run_refund(False)
        button_message, button_state = await self._run_refund(True)
        self.assertEqual(button_message.removeprefix("✅ "), slash_message)
        self.assertEqual(button_state, slash_state)

    async def _run_add_answer(self, use_button: bool):
        db, data_manager, player_manager, game = self._make_stack()
        game.handle_guess(202, "Target", "Accepted spelling")

        morning_task = MagicMock()
        evening_task = MagicMock()
        morning_task.is_running.return_value = False
        evening_task.is_running.return_value = False
        bot = SimpleNamespace(
            game=game,
            data_manager=data_manager,
            player_manager=player_manager,
            morning_message_task=morning_task,
            evening_message_task=evening_task,
        )
        try:
            if use_button:
                modal = AddAnswerModal(bot)
                modal.answer_input._value = "Accepted spelling"
                preview_interaction = self._interaction(100)
                await modal.on_submit(preview_interaction)
                view = preview_interaction.followup.send.call_args.kwargs["view"]
                button = next(
                    child
                    for child in view.children
                    if getattr(child, "custom_id", None) == "admin:add_answer_apply"
                )
                apply_interaction = self._interaction(100)
                await button.callback(apply_interaction)
                public = apply_interaction.channel.send.call_args.args[0]
            else:
                cog = Admin(bot)
                ctx = MagicMock()
                ctx.author.id = 100
                ctx.interaction.response.defer = AsyncMock()
                ctx.interaction.followup.send = AsyncMock()
                ctx.channel.send = AsyncMock()
                await cog.add_answer.callback(
                    cog, ctx, answer_text="Accepted spelling", apply=True
                )
                public = ctx.channel.send.call_args.args[0]

            return public, self._game_snapshot(data_manager, player_manager, game)
        finally:
            db.close()

    async def test_answer_correction_slash_and_modal_have_matching_outcomes(self):
        slash_message, slash_state = await self._run_add_answer(False)
        button_message, button_state = await self._run_add_answer(True)
        self.assertEqual(button_message, slash_message)
        self.assertEqual(button_state, slash_state)

    async def _run_skip(self, use_button: bool):
        class FakeGame:
            def __init__(self):
                self.daily_q = "Old question"
                self.reset_calls = 0

            def reset_daily_question(self):
                self.reset_calls += 1
                self.daily_q = "New question"
                return True

            @staticmethod
            def format_question(question):
                return question

        game = FakeGame()
        bot = SimpleNamespace(game=game)
        if use_button:
            view = SkipConfirmationView(bot)
            button = next(
                child
                for child in view.children
                if getattr(child, "custom_id", None) == "admin:skip_confirm"
            )
            interaction = self._interaction(100)
            await button.callback(interaction)
            public = interaction.channel.send.call_args.args[0]
        else:
            cog = Admin(bot)
            ctx = MagicMock()
            ctx.defer = AsyncMock()
            ctx.send = AsyncMock()
            await cog.skip.callback(cog, ctx)
            public = ctx.send.call_args.args[0]
        return public, game.reset_calls

    async def test_skip_slash_and_confirmation_have_matching_outcomes(self):
        slash = await self._run_skip(False)
        button = await self._run_skip(True)
        self.assertEqual(button, slash)
