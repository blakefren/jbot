import datetime
import unittest
from unittest.mock import patch, MagicMock, mock_open

from data.readers.question import Question
from data.readers.question_selector import QuestionSelector
from src.core.gemini_manager import GeminiManager
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("US/Pacific")


class TestQuestionSelector(unittest.TestCase):
    def setUp(self):
        self.questions = [
            Question("Q1", "A1", "C1", 100),
            Question("Q2", "A2", "C2", 200),
            Question("Q3", "A3", "C3", 300),
        ]
        self.mock_gemini_manager = MagicMock(spec=GeminiManager)

    def test_init_with_gemini(self):
        selector = QuestionSelector(
            self.questions, gemini_manager=self.mock_gemini_manager
        )
        self.assertEqual(selector.gemini_manager, self.mock_gemini_manager)

    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data='Riddle: [Riddle]\nHint: [Hint]\nAnswer: [Answer]\n[Insert Your Desired Difficulty Here, e.g., "Medium"]',
    )
    def test_get_riddle_from_gemini_success(self, mock_file):
        self.mock_gemini_manager.generate_content.return_value = (
            "Riddle: I have cities, but no houses.\n"
            "Hint: I am often folded.\n"
            "Answer: A map"
        )
        selector = QuestionSelector([], gemini_manager=self.mock_gemini_manager)

        question = selector.get_riddle_from_gemini("Medium")

        self.assertIsInstance(question, Question)
        self.assertEqual(question.question, "I have cities, but no houses.")
        self.assertEqual(question.answer, "A map")
        self.assertEqual(question.hint, "I am often folded.")
        self.assertEqual(question.category, "Riddle")
        # File is opened with an absolute path via os.path.join
        self.assertTrue(mock_file.called)
        self.mock_gemini_manager.generate_content.assert_called_once()

    def test_get_riddle_from_gemini_no_manager(self):
        selector = QuestionSelector([])  # No gemini_manager
        with self.assertRaises(ValueError):
            selector.get_riddle_from_gemini("Easy")

    @patch("logging.error")
    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_get_riddle_from_gemini_file_not_found(self, mock_open, mock_logging):
        selector = QuestionSelector([], gemini_manager=self.mock_gemini_manager)
        result = selector.get_riddle_from_gemini("Easy")
        self.assertIsNone(result)
        mock_logging.assert_called_with("Riddle prompt file not found.")

    @patch("logging.error")
    @patch("builtins.open", new_callable=mock_open, read_data="prompt")
    def test_get_riddle_from_gemini_api_failure(self, mock_open, mock_logging):
        self.mock_gemini_manager.generate_content.return_value = None
        selector = QuestionSelector([], gemini_manager=self.mock_gemini_manager)
        result = selector.get_riddle_from_gemini("Hard")
        self.assertIsNone(result)
        mock_logging.assert_called_with("Failed to get response from Gemini.")

    @patch("logging.error")
    @patch("builtins.open", new_callable=mock_open, read_data="prompt")
    def test_get_riddle_from_gemini_parsing_error(self, mock_open, mock_logging):
        self.mock_gemini_manager.generate_content.return_value = (
            "This is not a valid riddle format"
        )
        selector = QuestionSelector([], gemini_manager=self.mock_gemini_manager)
        result = selector.get_riddle_from_gemini("Medium")
        self.assertIsNone(result)
        self.assertIn(
            "Failed to parse riddle from Gemini response", mock_logging.call_args[0][0]
        )

    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="Riddle: [Insert your riddle here]\nAnswer: [Insert your answer here]",
    )
    def test_get_hint_from_gemini_success(self, mock_file):
        self.mock_gemini_manager.generate_content.return_value = "Hint: It's a thing."
        selector = QuestionSelector([], gemini_manager=self.mock_gemini_manager)
        question = Question("What is a thing?", "A thing", "Category", 100)

        hint = selector.get_hint_from_gemini(question)

        self.assertEqual(hint, "It's a thing.")
        # File is opened with an absolute path via os.path.join
        self.assertTrue(mock_file.called)
        self.mock_gemini_manager.generate_content.assert_called_once()
        # Check that the prompt was correctly formatted
        call_args = self.mock_gemini_manager.generate_content.call_args
        prompt = call_args[0][0]
        self.assertIn("What is a thing?", prompt)
        self.assertIn("A thing", prompt)

    def test_get_hint_from_gemini_no_manager(self):
        selector = QuestionSelector([])  # No gemini_manager
        question = Question("Q", "A", "C", 1)
        with self.assertRaisesRegex(ValueError, "Gemini manager is not configured."):
            selector.get_hint_from_gemini(question)

    @patch("logging.error")
    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_get_hint_from_gemini_file_not_found(self, mock_open, mock_logging):
        selector = QuestionSelector([], gemini_manager=self.mock_gemini_manager)
        question = Question("Q", "A", "C", 1)
        result = selector.get_hint_from_gemini(question)
        self.assertIsNone(result)
        mock_logging.assert_called_with("Hint prompt file not found.")

    @patch("logging.error")
    @patch("builtins.open", new_callable=mock_open, read_data="prompt")
    def test_get_hint_from_gemini_api_failure(self, mock_open, mock_logging):
        self.mock_gemini_manager.generate_content.return_value = None
        selector = QuestionSelector([], gemini_manager=self.mock_gemini_manager)
        question = Question("Q", "A", "C", 1)
        result = selector.get_hint_from_gemini(question)
        self.assertIsNone(result)
        mock_logging.assert_called_with("Failed to get response from Gemini for hint.")

    @patch("logging.error")
    @patch("builtins.open", new_callable=mock_open, read_data="prompt")
    def test_get_hint_from_gemini_parsing_error(self, mock_open, mock_logging):
        self.mock_gemini_manager.generate_content.return_value = (
            "This is not a valid hint format"
        )
        selector = QuestionSelector([], gemini_manager=self.mock_gemini_manager)
        question = Question("Q", "A", "C", 1)
        result = selector.get_hint_from_gemini(question)
        self.assertIsNone(result)
        self.assertIn(
            "Failed to parse hint from Gemini response", mock_logging.call_args[0][0]
        )

    def test_init(self):
        selector = QuestionSelector(self.questions)
        self.assertEqual(selector.questions, self.questions)
        self.assertFalse(hasattr(selector, "mode"))

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

    def test_init_no_questions_warning(self):
        with patch("logging.warning") as mock_logging:
            QuestionSelector([])
            mock_logging.assert_called_with(
                "QuestionSelector initialized with no questions."
            )

    @patch("data.readers.question_selector.randint")
    def test_get_random_question_with_exclude_hashes(self, mock_randint):
        """Test that get_random_question excludes questions with specified hashes."""
        mock_randint.return_value = 0
        selector = QuestionSelector(self.questions)

        # Exclude the first two questions by their hashes
        exclude_hashes = {str(self.questions[0].id), str(self.questions[1].id)}
        question = selector.get_random_question(exclude_hashes=exclude_hashes)

        # Should return the third question (only one available)
        self.assertEqual(question, self.questions[2])

    @patch("logging.warning")
    @patch("data.readers.question_selector.randint")
    def test_get_random_question_all_excluded_falls_back(
        self, mock_randint, mock_logging
    ):
        """Test that get_random_question falls back to full pool when all are excluded."""
        mock_randint.return_value = 1
        selector = QuestionSelector(self.questions)

        # Exclude all questions
        exclude_hashes = {str(q.id) for q in self.questions}
        question = selector.get_random_question(exclude_hashes=exclude_hashes)

        # Should fall back to full pool and return a question
        self.assertEqual(question, self.questions[1])
        mock_logging.assert_called_with(
            "All questions have been used. Selecting from full pool."
        )

    @patch("data.readers.question_selector.randint")
    def test_get_random_question_empty_exclude_hashes(self, mock_randint):
        """Test that get_random_question works with empty exclude set."""
        mock_randint.return_value = 0
        selector = QuestionSelector(self.questions)

        question = selector.get_random_question(exclude_hashes=set())
        self.assertEqual(question, self.questions[0])

    @patch("builtins.open", new_callable=mock_open, read_data="prompt")
    def test_validate_question_valid(self, mock_file):
        self.mock_gemini_manager.generate_content.return_value = "NO"
        selector = QuestionSelector(
            self.questions, gemini_manager=self.mock_gemini_manager
        )

        result = selector.validate_question(self.questions[0])

        self.assertTrue(result)
        self.mock_gemini_manager.generate_content.assert_called_once()

    @patch("builtins.open", new_callable=mock_open, read_data="prompt")
    def test_validate_question_invalid(self, mock_file):
        self.mock_gemini_manager.generate_content.return_value = "YES"
        selector = QuestionSelector(
            self.questions, gemini_manager=self.mock_gemini_manager
        )

        result = selector.validate_question(self.questions[0])

        self.assertFalse(result)
        self.mock_gemini_manager.generate_content.assert_called_once()

    def test_validate_question_no_manager(self):
        selector = QuestionSelector(self.questions)  # No manager
        result = selector.validate_question(self.questions[0])
        self.assertTrue(result)

    @patch("builtins.open", new_callable=mock_open, read_data="prompt")
    def test_validate_question_api_failure(self, mock_file):
        self.mock_gemini_manager.generate_content.return_value = None
        selector = QuestionSelector(
            self.questions, gemini_manager=self.mock_gemini_manager
        )

        result = selector.validate_question(self.questions[0])

        self.assertTrue(result)  # Fail open

    @patch("data.readers.question_selector.randint")
    def test_get_random_question_retries_invalid(self, mock_randint):
        selector = QuestionSelector(
            self.questions, gemini_manager=self.mock_gemini_manager
        )

        # Mock randint to return 0 then 1
        mock_randint.side_effect = [0, 1]

        with patch.object(
            selector, "validate_question", side_effect=[False, True]
        ) as mock_validate:
            question = selector.get_random_question()

            self.assertEqual(question, self.questions[1])
            self.assertEqual(mock_validate.call_count, 2)


if __name__ == "__main__":
    unittest.main()
