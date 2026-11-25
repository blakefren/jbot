import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from data.readers.question import Question
from src.cogs.trivia import Trivia
from tests.src.cogs._game_stack import build_game_stack


class TestTriviaCog(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = build_game_stack(self)
        self.game = self.stack.game
        self.data_manager = self.stack.data_manager
        self.player_manager = self.stack.player_manager
        self.cog = Trivia(SimpleNamespace(game=self.game))

    @staticmethod
    def _ctx(user_id=123, name="Test User"):
        ctx = AsyncMock()
        ctx.author.id = user_id
        ctx.author.display_name = name
        ctx.author.mention = f"<@{user_id}>"
        return ctx

    async def _answer(self, ctx, guess):
        await self.cog.answer.callback(self.cog, ctx, guess=guess)

    def _stored_guesses(self, user_id=123):
        return [
            (g["guess_text"], bool(g["is_correct"]))
            for g in self.data_manager.get_guesses_for_daily_question(
                self.game.daily_question_id
            )
            if g["player_id"] == str(user_id)
        ]

    async def test_answer_command_correct(self):
        ctx = self._ctx()

        await self._answer(ctx, "4")

        score = self.player_manager.get_player("123").score
        self.assertGreater(score, 0)
        self.assertEqual(self._stored_guesses(), [("4", True)])
        ctx.interaction.followup.send.assert_called_once_with(
            "Correct! Nicely done.\n**Answer:** 4\n\nGuesses:\n1. 4"
        )
        ctx.channel.send.assert_called_once()
        self.assertTrue(
            ctx.channel.send.call_args.args[0].startswith(
                f"<@123> solved it in 1! (+**{score}** pts)"
            )
        )

    async def test_answer_command_incorrect(self):
        ctx = self._ctx()

        await self._answer(ctx, "wrong answer")

        self.assertEqual(self._stored_guesses(), [("wrong answer", False)])
        self.assertEqual(self.player_manager.get_player("123").score, 0)
        ctx.interaction.followup.send.assert_called_once_with(
            "Sorry, that was incorrect.\n\nGuesses:\n1. wrong answer"
        )
        ctx.channel.send.assert_not_called()

    async def test_answer_command_long_history_still_sends_feedback(self):
        for user_id, guess, is_correct in ((123, "nope", False), (124, "4", True)):
            with self.subTest(is_correct=is_correct):
                self.player_manager.get_or_create_player(str(user_id), "Player")
                for i in range(30):
                    self.data_manager.log_player_guess(
                        str(user_id),
                        "Player",
                        self.game.daily_question_id,
                        f"guess {i:03d} " + "x" * 100,
                        False,
                    )
                ctx = self._ctx(user_id)

                await self._answer(ctx, guess)

                message = ctx.interaction.followup.send.call_args.args[0]
                self.assertLessEqual(len(message), 2000)
                self.assertIn("(truncated)", message)
                self.assertIn("Correct!" if is_correct else "incorrect", message)
                if is_correct:
                    ctx.channel.send.assert_awaited_once()
                else:
                    ctx.channel.send.assert_not_awaited()

    async def test_answer_command_no_question(self):
        stack = build_game_stack(self, start_day=False)
        cog = Trivia(SimpleNamespace(game=stack.game))
        ctx = self._ctx()

        await cog.answer.callback(cog, ctx, guess="any answer")

        ctx.interaction.followup.send.assert_called_once_with(
            "There is no active question."
        )
        self.assertEqual(stack.db.execute_query("SELECT * FROM guesses"), [])

    async def test_answer_command_already_answered_correctly(self):
        await self._answer(self._ctx(), "4")
        score = self.player_manager.get_player("123").score
        ctx = self._ctx()

        await self._answer(ctx, "4")

        ctx.interaction.followup.send.assert_called_once_with(
            "You already solved today."
        )
        ctx.channel.send.assert_not_called()
        self.assertEqual(self._stored_guesses(), [("4", True)])
        self.assertEqual(self.player_manager.get_player("123").score, score)

    async def test_answer_command_no_daily_question_id(self):
        self.game.daily_question_id = None
        ctx = self._ctx()

        await self._answer(ctx, "4")

        ctx.interaction.followup.send.assert_called_once_with(
            "Correct! Nicely done.\n**Answer:** 4\n\nGuesses:\nNo guesses yet."
        )

    async def test_answer_command_generic_exception(self):
        ctx = self._ctx()

        with patch.object(
            self.game, "handle_guess", side_effect=Exception("Database error")
        ):
            await self._answer(ctx, "any guess")

        ctx.interaction.followup.send.assert_called_once_with(
            "An error occurred while processing your answer. Please try again later."
        )

    async def test_answer_command_multiple_guesses_deduplicated(self):
        for guess in ("Apple", "Banana", "apple"):
            await self._answer(self._ctx(), guess)
        ctx = self._ctx()

        await self._answer(ctx, "cherry")

        ctx.interaction.followup.send.assert_called_once_with(
            "Sorry, that was incorrect.\n\nGuesses:\n1. apple\n2. banana\n3. cherry"
        )

    async def test_answer_command_filters_by_daily_question_id(self):
        await self._answer(self._ctx(), "Old guess")
        self.data_manager.log_daily_question(
            Question("Second question?", "Other", "Misc", 100), force_new=True
        )
        self.game.set_daily_question()
        self.assertEqual(self.game.daily_question_id, 2)
        ctx = self._ctx()

        await self._answer(ctx, "Current guess")

        message = ctx.interaction.followup.send.call_args.args[0]
        self.assertIn("current guess", message)
        self.assertNotIn("old guess", message.lower())


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
