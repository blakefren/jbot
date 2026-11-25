import unittest
from src.core.guess_handler import GuessHandler
from data.readers.question import Question
from tests.src.core._powerup_helpers import make_config, make_stack


class TestGuessHandlerAlternatives(unittest.TestCase):
    def setUp(self):
        self.daily_question = Question("Q", "Original Answer", "C", 100)
        self.stack = make_stack(
            self,
            [("1", "p1", 0, 0), ("2", "p2", 0, 0), ("admin", "Admin", 0, 0)],
        )
        self.data_manager = self.stack.data_manager
        self.player_manager = self.stack.player_manager
        # A question stored without a daily entry keeps questions.id and
        # daily_questions.id different, so lookups by the wrong id would fail.
        self.data_manager.log_daily_question(
            Question("Filler", "Filler", "C", 100), mark_as_used_only=True
        )
        self.daily_question_id = self.stack.new_question_day(self.daily_question)
        self.question_db_id = self.stack.question_db_id
        self.assertNotEqual(self.question_db_id, self.daily_question_id)
        self.config = make_config()

    def _make_handler(self):
        return GuessHandler(
            self.data_manager,
            self.player_manager,
            self.daily_question,
            self.daily_question_id,
            {},
            config=self.config,
            question_db_id=self.question_db_id,
        )

    def _add_alternative(self, answer):
        self.data_manager.add_alternative_answer(self.question_db_id, answer, "admin")

    def _guess(self, handler, player_id, guess):
        is_correct, _, _, _ = handler.handle_guess(player_id, f"p{player_id}", guess)
        return is_correct

    def test_original_answer_still_works(self):
        self._add_alternative("Alt Answer")
        self.assertTrue(self._guess(self._make_handler(), 1, "Original Answer"))

    def test_alternative_answer_works(self):
        self._add_alternative("Alt Answer")
        self.assertTrue(self._guess(self._make_handler(), 1, "Alt Answer"))

    def test_alternative_answer_works_normalized(self):
        self._add_alternative("Alt Answer")
        self.assertTrue(self._guess(self._make_handler(), 1, "alt answer"))

    def test_numeric_alternative_works(self):
        self._add_alternative("800")
        self.assertTrue(self._guess(self._make_handler(), 1, "800"))

    def test_wrong_answer_still_wrong(self):
        self._add_alternative("Alt Answer")
        self.assertFalse(self._guess(self._make_handler(), 1, "Wrong"))
        history = self.data_manager.read_guess_history("1")
        self.assertFalse(history[0]["is_correct"])

    def test_database_lookup_uses_question_id_not_daily_question_id(self):
        self._add_alternative("Alt Answer")

        self.assertTrue(self._guess(self._make_handler(), "1", "Alt Answer"))

        history = self.data_manager.read_guess_history("1")
        self.assertTrue(history[0]["is_correct"])
        self.assertEqual(history[0]["daily_question_id"], self.daily_question_id)

    # ------------------------------------------------------------------
    # Regression: Bug A - stale alternative_answers after /admin add_answer
    # ------------------------------------------------------------------

    def test_newly_added_alt_answer_recognized_without_rebuild(self):
        """
        Regression: GuessHandler must always check the live DB for alternative answers
        rather than using a cached list from construction time.

        Old behaviour: self.alternative_answers was loaded once in __init__.
        After /admin add_answer added a new alt, the running handler still had the
        old (empty or stale) list, so guesses matching the new alt were logged wrong.

        Fixed: handle_guess reloads alt answers from DB on every call.
        """
        # At construction time, no alt answers exist
        handler = self._make_handler()

        # Simulate /admin add_answer updating the DB mid-game
        self._add_alternative("New Alt Answer")

        # Player guesses the new alt after it was added - should be credited
        self.assertTrue(
            self._guess(handler, 1, "New Alt Answer"),
            "Guess matching a newly-added alt answer must be recognised without "
            "rebuilding the GuessHandler",
        )
        history = self.data_manager.read_guess_history("1")
        self.assertTrue(history[0]["is_correct"])

    def test_stale_cached_list_is_not_used(self):
        """
        Complement: the handler constructed with an old cache should NOT use that cache.
        Verifies that adding a new alt answer to DB is sufficient for recognition.
        """
        # At construction time, alt answers contain one entry
        self._add_alternative("Old Alt")
        handler = self._make_handler()

        # Later, DB is updated to have a different alt (simulates add_answer)
        self.stack.db.execute_update(
            "DELETE FROM alternative_answers WHERE answer_text = ?", ("Old Alt",)
        )
        self._add_alternative("New Alt Answer")

        # "Old Alt" is no longer in DB - should not match
        self.assertFalse(
            self._guess(handler, 1, "Old Alt"),
            "Old cached alt answer should not be used if it is no longer in DB",
        )

        # "New Alt Answer" is in DB - should match
        self.assertTrue(
            self._guess(handler, 2, "New Alt Answer"),
            "Newly added alt answer should be recognised via live DB reload",
        )
