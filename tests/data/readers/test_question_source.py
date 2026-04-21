import unittest
from unittest.mock import MagicMock, patch, mock_open
from data.readers.question import Question
from data.readers.question_source import StaticQuestionSource, GeminiQuestionSource, LazyFileQuestionSource
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
        self.assertTrue(question.category.startswith("Riddle (medium)"))
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


class TestLazyFileQuestionSource(unittest.TestCase):
    def setUp(self):
        self.questions = [
            Question("Q1", "A1", "C1", 100),
            Question("Q2", "A2", "C2", 200),
        ]
        self.mock_loader = MagicMock(return_value=self.questions)
        self.source = LazyFileQuestionSource(
            "test_lazy", 50.0, self.mock_loader, {"file_path": "/fake/path.csv"}
        )

    def test_loader_not_called_at_init(self):
        """Dataset should not be loaded at construction time."""
        self.mock_loader.assert_not_called()

    def test_get_question_calls_loader(self):
        """get_question() should invoke the loader exactly once per call."""
        self.source.get_question()
        self.mock_loader.assert_called_once_with(file_path="/fake/path.csv")

    def test_loader_called_each_time(self):
        """Each call to get_question() reloads the dataset (no caching)."""
        self.source.get_question()
        self.source.get_question()
        self.assertEqual(self.mock_loader.call_count, 2)

    def test_get_question_returns_question_from_loaded_data(self):
        question = self.source.get_question()
        self.assertIn(question, self.questions)

    def test_get_question_excludes_hashes(self):
        exclude = {str(self.questions[0].id)}
        for _ in range(10):
            question = self.source.get_question(exclude_hashes=exclude)
            self.assertEqual(question, self.questions[1])

    def test_get_question_exhausted_uses_full_pool(self):
        exclude = {str(q.id) for q in self.questions}
        question = self.source.get_question(exclude_hashes=exclude)
        self.assertIn(question, self.questions)

    def test_get_question_empty_loader_returns_none(self):
        source = LazyFileQuestionSource("empty", 50.0, MagicMock(return_value=[]), {})
        self.assertIsNone(source.get_question())

    def test_default_points_override(self):
        source = LazyFileQuestionSource(
            "points", 50.0, self.mock_loader, {}, default_points=999
        )
        question = source.get_question()
        self.assertEqual(question.clue_value, 999)

    def test_loader_kwargs_passed_correctly(self):
        kwargs = {"file_path": "/data/test.tsv", "difficulty": "medium", "final_jeopardy_score": 300}
        source = LazyFileQuestionSource("jeopardy", 75.0, self.mock_loader, kwargs)
        source.get_question()
        self.mock_loader.assert_called_once_with(**kwargs)
