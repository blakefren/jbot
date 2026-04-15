import unittest
from unittest.mock import MagicMock
from src.core.guess_handler import GuessHandler
from data.readers.question import Question


class TestGuessHandlerAlternatives(unittest.TestCase):
    def setUp(self):
        self.data_manager = MagicMock()
        self.daily_question = Question("Q", "Original Answer", "C", 100)
        self.daily_question_id = 1
        self.player_manager = MagicMock()
        self.player_manager.get_player.return_value = None
        self.managers = {}

        # Mock alternative answers
        self.data_manager.get_alternative_answers.return_value = ["Alt Answer", "800"]

        # Mock required data_manager methods to return valid types
        self.data_manager.get_correct_guess_count.return_value = 0
        self.data_manager.read_guess_history.return_value = []
        self.data_manager.get_hint_sent_timestamp.return_value = None
        self.data_manager.get_last_correct_guess_date.return_value = None

        self.guess_handler = GuessHandler(
            self.data_manager,
            self.player_manager,
            self.daily_question,
            self.daily_question_id,
            self.managers,
        )

        # Mock config
        self.guess_handler.config = MagicMock()
        self.guess_handler.config.get.side_effect = lambda k, d=None: d

    def test_original_answer_still_works(self):
        is_correct, _, _, _ = self.guess_handler.handle_guess(
            1, "p1", "Original Answer"
        )
        self.assertTrue(is_correct)

    def test_alternative_answer_works(self):
        is_correct, _, _, _ = self.guess_handler.handle_guess(1, "p1", "Alt Answer")
        self.assertTrue(is_correct)

    def test_alternative_answer_works_normalized(self):
        is_correct, _, _, _ = self.guess_handler.handle_guess(1, "p1", "alt answer")
        self.assertTrue(is_correct)

    def test_numeric_alternative_works(self):
        is_correct, _, _, _ = self.guess_handler.handle_guess(1, "p1", "800")
        self.assertTrue(is_correct)

    def test_wrong_answer_still_wrong(self):
        is_correct, _, _, _ = self.guess_handler.handle_guess(1, "p1", "Wrong")
        self.assertFalse(is_correct)

    # ------------------------------------------------------------------
    # Regression: Bug A — stale alternative_answers after /admin add_answer
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
        self.data_manager.get_alternative_answers.return_value = []
        handler = GuessHandler(
            self.data_manager,
            self.player_manager,
            self.daily_question,
            self.daily_question_id,
            self.managers,
        )
        handler.config = MagicMock()
        handler.config.get.side_effect = lambda k, d=None: d

        # Simulate /admin add_answer updating the DB mid-game
        self.data_manager.get_alternative_answers.return_value = ["New Alt Answer"]

        # Player guesses the new alt after it was added — should be credited
        is_correct, _, _, _ = handler.handle_guess(1, "p1", "New Alt Answer")
        self.assertTrue(
            is_correct,
            "Guess matching a newly-added alt answer must be recognised without "
            "rebuilding the GuessHandler",
        )

    def test_stale_cached_list_is_not_used(self):
        """
        Complement: the handler constructed with an old cache should NOT use that cache.
        Verifies that adding a new alt answer to DB is sufficient for recognition.
        """
        # At construction time, alt answers contain one entry
        self.data_manager.get_alternative_answers.return_value = ["Old Alt"]
        handler = GuessHandler(
            self.data_manager,
            self.player_manager,
            self.daily_question,
            self.daily_question_id,
            self.managers,
        )
        handler.config = MagicMock()
        handler.config.get.side_effect = lambda k, d=None: d

        # Later, DB is updated to have a different alt (simulates add_answer)
        self.data_manager.get_alternative_answers.return_value = ["New Alt Answer"]

        # "Old Alt" is no longer in DB — should not match
        is_old_correct, _, _, _ = handler.handle_guess(1, "p1", "Old Alt")
        self.assertFalse(
            is_old_correct,
            "Old cached alt answer should not be used if it is no longer in DB",
        )

        # "New Alt Answer" is in DB — should match
        self.data_manager.read_guess_history.return_value = []  # reset for second call
        is_new_correct, _, _, _ = handler.handle_guess(2, "p2", "New Alt Answer")
        self.assertTrue(
            is_new_correct,
            "Newly added alt answer should be recognised via live DB reload",
        )
