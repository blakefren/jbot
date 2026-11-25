import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from data.readers.question import Question
from src.cogs.admin import Admin
from tests.src.cogs._game_stack import build_game_stack


class TestAdminAddAnswer(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = build_game_stack(
            self,
            players=(("111", "Player1"), ("222", "Player2"), ("999", "Sleepy")),
            question=Question("Test question?", "Test answer", "Test", 100),
        )
        self.game = self.stack.game
        self.data_manager = self.stack.data_manager
        self.player_manager = self.stack.player_manager

        # The Discord bot and its scheduler tasks are the external boundary.
        self.bot = MagicMock()
        self.bot.morning_message_task = MagicMock()
        self.bot.evening_message_task = MagicMock()
        # Tasks not running -> answer not revealed
        self.bot.morning_message_task.is_running.return_value = False
        self.bot.evening_message_task.is_running.return_value = False
        self.bot.game = self.game
        self.bot.player_manager = self.player_manager
        self.bot.data_manager = self.data_manager

        self.cog = Admin(self.bot)

        self.ctx = MagicMock()
        self.ctx.author.id = 12345
        self.ctx.send = AsyncMock()
        self.ctx.channel.send = AsyncMock()
        self.ctx.interaction = MagicMock()
        self.ctx.interaction.response.defer = AsyncMock()
        self.ctx.interaction.followup.send = AsyncMock()

    def _players_guess(self, text):
        """Both players guess `text`, which is wrong until it is accepted."""
        self.game.handle_guess(111, "Player1", text)
        self.game.handle_guess(222, "Player2", text)

    def _scores(self):
        return {
            player_id: self.player_manager.get_player(player_id).score
            for player_id in ("111", "222")
        }

    def _set_revealed(self):
        """Configure task doubles so the answer counts as revealed."""
        now = datetime.now()
        self.bot.morning_message_task.is_running.return_value = True
        self.bot.evening_message_task.is_running.return_value = True
        self.bot.morning_message_task.next_iteration = now + timedelta(hours=1)
        self.bot.evening_message_task.next_iteration = now + timedelta(hours=12)

    async def _add_answer(self, text, apply):
        await self.cog.add_answer.callback(
            self.cog, self.ctx, answer_text=text, apply=apply
        )

    def _ephemeral_text(self):
        return self.ctx.interaction.followup.send.call_args[0][0]

    def _public_text(self):
        return self.ctx.channel.send.call_args[0][0]

    async def test_add_answer_apply_success(self):
        """apply=True: single public message with @mentions; ephemeral is just 'Done.'"""
        self._players_guess("New Answer")
        before = self._scores()
        self.assertEqual(before, {"111": 0, "222": 0})

        await self._add_answer("New Answer", apply=True)

        self.ctx.interaction.response.defer.assert_called_once_with(ephemeral=True)
        self.assertEqual(
            self.data_manager.get_alternative_answers(self.game.question_db_id),
            ["New Answer"],
        )
        after = self._scores()
        self.assertTrue(all(score > 0 for score in after.values()))
        adjustments = {
            row["player_id"]: row["amount"]
            for row in self.stack.db.execute_query(
                "SELECT player_id, amount FROM score_adjustments"
            )
        }
        self.assertEqual(adjustments, after)

        # Ephemeral reply is just a silent "Done."
        self.assertEqual(self._ephemeral_text(), "Done.")

        # Public message uses @mentions and contains the summary
        self.ctx.channel.send.assert_called_once()
        public_text = self._public_text()
        self.assertIn("Score Adjustment:", public_text)
        self.assertIn(f"Total points refunded: {sum(after.values())}.", public_text)
        self.assertIn("<@111>", public_text)
        self.assertIn("<@222>", public_text)
        # Answer not revealed — answer text must NOT appear
        self.assertNotIn("New Answer", public_text)

    async def test_add_answer_dry_run(self):
        """apply=False: single ephemeral message with [DRY RUN], plain names, no public."""
        self._players_guess("New Answer")

        await self._add_answer("New Answer", apply=False)

        ephemeral_text = self._ephemeral_text()
        self.assertIn("[DRY RUN]", ephemeral_text)
        self.assertIn("Would update 2 players.", ephemeral_text)
        # Plain name used — no @mention
        self.assertIn("Player1", ephemeral_text)
        self.assertNotIn("<@111>", ephemeral_text)

        self.ctx.channel.send.assert_not_called()
        self.assertEqual(self._scores(), {"111": 0, "222": 0})
        self.assertEqual(
            self.data_manager.get_alternative_answers(self.game.question_db_id), []
        )
        self.assertEqual(
            self.stack.db.execute_query("SELECT * FROM score_adjustments"), []
        )

    async def test_add_answer_error(self):
        """Test add_answer handles errors gracefully."""
        self.bot.game = build_game_stack(self, start_day=False).game

        await self._add_answer("Fail Answer", apply=True)

        self.ctx.interaction.followup.send.assert_called_once()
        self.assertIn("Error: No daily question found.", self._ephemeral_text())
        self.ctx.channel.send.assert_not_called()

    # ------------------------------------------------------------------
    # Answer visibility
    # ------------------------------------------------------------------

    async def test_apply_not_revealed_answer_hidden_from_public(self):
        """apply=True, not revealed: answer text must not appear in the public message."""
        self._players_guess("Secret")
        await self._add_answer("Secret", apply=True)
        self.assertNotIn("Secret", self._public_text())

    async def test_apply_revealed_shows_spoiler_in_public(self):
        """apply=True, after reveal: public message shows answer under spoiler tags."""
        self._set_revealed()
        self._players_guess("SecretAnswer")
        await self._add_answer("SecretAnswer", apply=True)
        self.assertIn("||SecretAnswer||", self._public_text())

    async def test_dry_run_not_revealed_answer_hidden_from_ephemeral(self):
        """apply=False, not revealed: answer text must not appear in ephemeral message."""
        self._players_guess("Secret")
        await self._add_answer("Secret", apply=False)
        self.assertNotIn("Secret", self._ephemeral_text())

    async def test_dry_run_revealed_shows_answer_in_ephemeral(self):
        """apply=False, after reveal: ephemeral shows answer (with spoiler) so admin sees it."""
        self._set_revealed()
        self._players_guess("SecretAnswer")
        await self._add_answer("SecretAnswer", apply=False)
        self.assertIn("||SecretAnswer||", self._ephemeral_text())

    # ------------------------------------------------------------------
    # Player tagging
    # ------------------------------------------------------------------

    async def test_apply_public_uses_mentions_not_plain_names(self):
        """apply=True: public message uses <@id> mentions, not bare player names."""
        self._players_guess("Ans")
        await self._add_answer("Ans", apply=True)
        public_text = self._public_text()
        self.assertIn("<@111>", public_text)
        self.assertNotIn("Player1", public_text)

    async def test_dry_run_ephemeral_uses_plain_names_not_mentions(self):
        """apply=False: ephemeral must not contain @mentions."""
        self._players_guess("Ans")
        await self._add_answer("Ans", apply=False)
        self.assertNotIn("<@", self._ephemeral_text())

    # ------------------------------------------------------------------
    # Rest-cleared players
    # ------------------------------------------------------------------

    def _resting_player_guesses(self, text):
        question_id = self.game.daily_question_id
        self.data_manager.log_powerup_usage("999", "rest", None, question_id)
        self.data_manager.log_player_guess("999", "Sleepy", question_id, text, False)

    async def test_apply_rest_cleared_mentioned_in_public(self):
        """apply=True: resting players whose guess matched are @mentioned with rest note."""
        self._resting_player_guesses("Ans")
        await self._add_answer("Ans", apply=True)
        public_text = self._public_text()
        self.assertIn("<@999>", public_text)
        self.assertIn("Rest revoked", public_text)

    async def test_dry_run_rest_cleared_shows_name_in_ephemeral(self):
        """apply=False: resting players listed by name (no @mention) in dry-run ephemeral."""
        self._resting_player_guesses("Ans")
        await self._add_answer("Ans", apply=False)
        ephemeral_text = self._ephemeral_text()
        self.assertIn("Sleepy", ephemeral_text)
        self.assertIn("Rest revoked", ephemeral_text)
        self.assertNotIn("<@999>", ephemeral_text)


if __name__ == "__main__":
    unittest.main()
