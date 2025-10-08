import datetime
import unittest
from unittest.mock import patch

from data.readers.question import Question
from data.readers.question_selector import QuestionSelector
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("US/Pacific")


class TestQuestionSelector(unittest.TestCase):
    def setUp(self):
        self.questions = [
            Question("Q1", "A1", "C1", 100),
            Question("Q2", "A2", "C2", 200),
            Question("Q3", "A3", "C3", 300),
        ]

    def test_init(self):
        selector = QuestionSelector(self.questions, mode="daily")
        self.assertEqual(selector.questions, self.questions)
        self.assertEqual(selector.mode, "daily")

    @patch("data.readers.question_selector.datetime")
    def test_get_question_for_today_daily_mode(self, mock_datetime):
        # Mock the current time
        mock_now = datetime.datetime(2023, 10, 27, 12, 0, 0, tzinfo=TIMEZONE)
        mock_datetime.datetime.now.return_value = mock_now

        selector = QuestionSelector(self.questions, mode="daily")
        question = selector.get_question_for_today()

        # The index should be predictable based on the date's ordinal
        expected_index = mock_now.date().toordinal() % len(self.questions)
        self.assertEqual(question, self.questions[expected_index])

    def test_get_question_for_today_unimplemented_mode(self):
        selector = QuestionSelector(self.questions, mode="themed")
        with self.assertRaises(NotImplementedError):
            selector.get_question_for_today()

    @patch("data.readers.question_selector.randint")
    def test_get_random_question(self, mock_randint):
        mock_randint.return_value = 1  # Mock the random index
        selector = QuestionSelector(self.questions)
        question = selector.get_random_question()
        self.assertEqual(question, self.questions[1])

    def test_get_random_question_no_questions(self):
        selector = QuestionSelector([])
        question = selector.get_random_question()
        self.assertIsNone(question)

    def test_get_question_for_today_no_questions(self):
        selector = QuestionSelector([], mode="daily")
        with self.assertRaises(ValueError):
            selector.get_question_for_today()

    def test_init_no_questions_warning(self):
        with patch("builtins.print") as mock_print:
            QuestionSelector([])
            mock_print.assert_called_with(
                "Warning: QuestionSelector initialized with no questions."
            )


if __name__ == "__main__":
    unittest.main()
