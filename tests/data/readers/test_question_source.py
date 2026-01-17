import unittest
from unittest.mock import MagicMock, patch, mock_open
from data.readers.question import Question
from data.readers.question_source import StaticQuestionSource, GeminiQuestionSource
import os


class TestStaticQuestionSource(unittest.TestCase):
    def setUp(self):
        self.questions = [
            Question("Q1", "A1", "C1", 100),
            Question("Q2", "A2", "C2", 200),
        ]
        self.source = StaticQuestionSource("test_static", 50.0, self.questions)

    def test_get_question_returns_random_question(self):
        question = self.source.get_question()
        self.assertIn(question, self.questions)

    def test_get_question_excludes_hashes(self):
        exclude = {str(self.questions[0].id)}
        # Should only return Q2
        for _ in range(10):
            question = self.source.get_question(exclude_hashes=exclude)
            self.assertEqual(question, self.questions[1])

    def test_get_question_exhausted_returns_from_full_pool(self):
        exclude = {str(q.id) for q in self.questions}
        question = self.source.get_question(exclude_hashes=exclude)
        self.assertIn(question, self.questions)

    def test_get_question_empty_pool(self):
        source = StaticQuestionSource("empty", 50.0, [])
        self.assertIsNone(source.get_question())

    def test_default_points_override(self):
        source = StaticQuestionSource(
            "points", 50.0, self.questions, default_points=500
        )
        question = source.get_question()
        self.assertEqual(question.clue_value, 500)


class TestGeminiQuestionSource(unittest.TestCase):
    def setUp(self):
        self.mock_gemini = MagicMock()
        self.source = GeminiQuestionSource(
            "test_gemini", 20.0, self.mock_gemini, difficulty="Medium"
        )

    @patch("builtins.open", new_callable=mock_open, read_data="Prompt template")
    def test_get_question_success(self, mock_file):
        self.mock_gemini.generate_content.return_value = (
            "Riddle: My Riddle\nHint: My Hint\nAnswer: My Answer"
        )

        question = self.source.get_question()

        self.assertIsNotNone(question)
        self.assertEqual(question.question, "My Riddle")
        self.assertEqual(question.answer, "My Answer")
        self.assertEqual(question.hint, "My Hint")
        self.assertEqual(question.category, "Riddle (medium)")
        self.assertEqual(question.data_source, "gemini_medium")
        self.assertEqual(question.clue_value, 100)  # Default

    @patch("builtins.open", new_callable=mock_open, read_data="Prompt template")
    def test_get_question_with_points(self, mock_file):
        self.mock_gemini.generate_content.return_value = "Riddle: R\nHint: H\nAnswer: A"
        source = GeminiQuestionSource(
            "gemini_points", 20.0, self.mock_gemini, default_points=300
        )
        question = source.get_question()
        self.assertEqual(question.clue_value, 300)

    def test_get_question_no_manager(self):
        source = GeminiQuestionSource("no_manager", 20.0, None)
        self.assertIsNone(source.get_question())

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_get_question_file_not_found(self, mock_file):
        self.assertIsNone(self.source.get_question())

    @patch("builtins.open", new_callable=mock_open, read_data="Prompt")
    def test_get_question_gemini_failure(self, mock_file):
        self.mock_gemini.generate_content.return_value = None
        self.assertIsNone(self.source.get_question())

    @patch("builtins.open", new_callable=mock_open, read_data="Prompt")
    def test_get_question_parse_error(self, mock_file):
        self.mock_gemini.generate_content.return_value = "Invalid format"
        self.assertIsNone(self.source.get_question())
