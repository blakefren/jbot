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
        self.managers = {}

        # Mock alternative answers
        self.data_manager.get_alternative_answers.return_value = ["Alt Answer", "800"]

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
