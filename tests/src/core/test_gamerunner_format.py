import unittest
from unittest.mock import MagicMock
from src.core.game_runner import GameRunner
from data.readers.question import Question


class TestGameRunnerFormatAnswer(unittest.TestCase):
    def setUp(self):
        self.mock_qs = MagicMock()
        self.mock_dm = MagicMock()
        self.runner = GameRunner(self.mock_qs, self.mock_dm)
        self.runner.daily_question_id = 123
        self.question = Question("Q", "Main Answer", "C", 100)

    def test_format_answer_no_alts(self):
        self.mock_dm.get_alternative_answers.return_value = []
        result = self.runner.format_answer(self.question)
        self.assertIn("Main Answer", result)
        self.assertNotIn("Also accepted", result)

    def test_format_answer_with_alts(self):
        self.mock_dm.get_alternative_answers.return_value = ["Alt1", "Alt2"]
        result = self.runner.format_answer(self.question)
        self.assertIn("Main Answer", result)
        self.assertIn("Also accepted", result)
        self.assertIn("Alt1", result)
        self.assertIn("Alt2", result)
