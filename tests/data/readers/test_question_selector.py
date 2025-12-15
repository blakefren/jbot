import datetime
import unittest
from unittest.mock import patch, MagicMock, mock_open

from data.readers.question import Question
from data.readers.question_selector import QuestionSelector
from data.readers.question_source import StaticQuestionSource
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
            questions=self.questions, gemini_manager=self.mock_gemini_manager
        )
        self.assertEqual(selector.gemini_manager, self.mock_gemini_manager)
        # Should create a default source
        self.assertEqual(len(selector.sources), 1)
        self.assertIsInstance(selector.sources[0], StaticQuestionSource)

    def test_init_with_sources(self):
        source1 = MagicMock()
        source2 = MagicMock()
        selector = QuestionSelector(sources=[source1, source2])
        self.assertEqual(selector.sources, [source1, source2])

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
        selector = QuestionSelector(
            questions=[], gemini_manager=self.mock_gemini_manager
        )

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
        selector = QuestionSelector(questions=[])  # No gemini_manager
        with self.assertRaises(ValueError):
            selector.get_riddle_from_gemini("Easy")

    @patch("logging.error")
    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_get_riddle_from_gemini_file_not_found(self, mock_open, mock_logging):
        selector = QuestionSelector(
            questions=[], gemini_manager=self.mock_gemini_manager
        )
        result = selector.get_riddle_from_gemini("Easy")
        self.assertIsNone(result)
        mock_logging.assert_called_with("Riddle prompt file not found.")

    @patch("logging.error")
    @patch("builtins.open", new_callable=mock_open, read_data="prompt")
    def test_get_riddle_from_gemini_api_failure(self, mock_open, mock_logging):
        self.mock_gemini_manager.generate_content.return_value = None
        selector = QuestionSelector(
            questions=[], gemini_manager=self.mock_gemini_manager
        )
        result = selector.get_riddle_from_gemini("Hard")
        self.assertIsNone(result)
        mock_logging.assert_called_with("Failed to get response from Gemini.")

    @patch("logging.error")
    @patch("builtins.open", new_callable=mock_open, read_data="prompt")
    def test_get_riddle_from_gemini_parsing_error(self, mock_open, mock_logging):
        self.mock_gemini_manager.generate_content.return_value = (
            "This is not a valid riddle format"
        )
        selector = QuestionSelector(
            questions=[], gemini_manager=self.mock_gemini_manager
        )
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
        selector = QuestionSelector(
            questions=[], gemini_manager=self.mock_gemini_manager
        )
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
        selector = QuestionSelector(questions=self.questions)
        # Should create a default source
        self.assertEqual(len(selector.sources), 1)
        self.assertIsInstance(selector.sources[0], StaticQuestionSource)
        self.assertEqual(selector.sources[0].questions, self.questions)

    @patch("data.readers.question_selector.random.uniform")
    def test_get_random_question(self, mock_uniform):
        # Legacy behavior test via default source
        selector = QuestionSelector(questions=self.questions)
        mock_uniform.return_value = 50  # Should pick the only source

        # We need to patch the source's get_question or random.choice inside it
        # But since we are testing QuestionSelector, we can rely on StaticQuestionSource working
        # However, StaticQuestionSource uses random.choice.

        with patch(
            "data.readers.question_source.random.choice", return_value=self.questions[1]
        ):
            question = selector.get_random_question()
            self.assertEqual(question, self.questions[1])

    def test_get_random_question_no_questions(self):
        selector = QuestionSelector(questions=[])
        question = selector.get_random_question()
        self.assertIsNone(question)

    def test_init_no_questions_warning(self):
        with patch("logging.warning") as mock_logging:
            QuestionSelector(questions=[])
            mock_logging.assert_called_with(
                "QuestionSelector initialized with no sources."
            )

    @patch("data.readers.question_selector.random.uniform")
    def test_get_random_question_weighted_selection(self, mock_uniform):
        source1 = MagicMock(spec=StaticQuestionSource)
        source1.weight = 10.0
        source1.name = "source1"
        source1.get_question.return_value = self.questions[0]

        source2 = MagicMock(spec=StaticQuestionSource)
        source2.weight = 90.0
        source2.name = "source2"
        source2.get_question.return_value = self.questions[1]

        selector = QuestionSelector(sources=[source1, source2])

        # Total weight = 100.
        # If uniform returns 5, it should pick source1 (0-10)
        mock_uniform.return_value = 5.0
        q = selector.get_random_question()
        self.assertEqual(q, self.questions[0])
        source1.get_question.assert_called_once()
        source2.get_question.assert_not_called()

        # If uniform returns 50, it should pick source2 (10-100)
        mock_uniform.return_value = 50.0
        source1.reset_mock()
        source2.reset_mock()
        q = selector.get_random_question()
        self.assertEqual(q, self.questions[1])
        source1.get_question.assert_not_called()
        source2.get_question.assert_called_once()

    def test_get_random_question_no_sources(self):
        selector = QuestionSelector(sources=[])
        self.assertIsNone(selector.get_random_question())

    @patch("builtins.open", new_callable=mock_open, read_data="prompt")
    def test_validate_question_valid(self, mock_file):
        self.mock_gemini_manager.generate_content.return_value = "NO"
        selector = QuestionSelector(
            questions=self.questions, gemini_manager=self.mock_gemini_manager
        )

        result = selector.validate_question(self.questions[0])

        self.assertTrue(result)
        self.mock_gemini_manager.generate_content.assert_called_once()

    @patch("builtins.open", new_callable=mock_open, read_data="prompt")
    def test_validate_question_invalid(self, mock_file):
        self.mock_gemini_manager.generate_content.return_value = "YES"
        selector = QuestionSelector(
            questions=self.questions, gemini_manager=self.mock_gemini_manager
        )

        result = selector.validate_question(self.questions[0])

        self.assertFalse(result)
        self.mock_gemini_manager.generate_content.assert_called_once()

    def test_validate_question_no_manager(self):
        selector = QuestionSelector(questions=self.questions)  # No manager
        result = selector.validate_question(self.questions[0])
        self.assertTrue(result)

    @patch("builtins.open", new_callable=mock_open, read_data="prompt")
    def test_validate_question_api_failure(self, mock_file):
        self.mock_gemini_manager.generate_content.return_value = None
        selector = QuestionSelector(
            questions=self.questions, gemini_manager=self.mock_gemini_manager
        )

        result = selector.validate_question(self.questions[0])

        self.assertTrue(result)  # Fail open

    @patch("data.readers.question_selector.random.uniform")
    def test_get_random_question_returns_invalid(self, mock_uniform):
        # Setup a source that returns a question
        source = MagicMock(spec=StaticQuestionSource)
        source.weight = 100
        source.name = "test"
        source.get_question.return_value = self.questions[0]

        selector = QuestionSelector(
            sources=[source], gemini_manager=self.mock_gemini_manager
        )
        mock_uniform.return_value = 50

        with patch.object(
            selector, "validate_question", return_value=False
        ) as mock_validate:
            question = selector.get_random_question()

            self.assertEqual(question, self.questions[0])
            self.assertFalse(question.is_valid)
            self.assertEqual(mock_validate.call_count, 1)


if __name__ == "__main__":
    unittest.main()
