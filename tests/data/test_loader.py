import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add the project root to the Python path to allow for absolute imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

from data.loader import load_questions
from data.readers.question import Question
from src.cfg.main import ConfigReader


class TestLoadQuestions(unittest.TestCase):
    def setUp(self):
        """Set up a mock ConfigReader for testing."""
        self.mock_config = MagicMock(spec=ConfigReader)
        # Define a dummy project root for the loader to use
        self.project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )

        # Mock get() method - will be overridden in tests as needed
        self.mock_config.get.side_effect = lambda key: {
            "JBOT_QUESTION_DATASET": "jeopardy",
            "JBOT_FINAL_JEOPARDY_SCORE_SUB": "2000",
        }.get(key)

        # get_dataset_path will be set per-test
        # Default behavior returns dummy path
        def default_get_dataset_path(dataset):
            return os.path.join(self.project_root, f"dummy_{dataset}")

        self.mock_config.get_dataset_path.side_effect = default_get_dataset_path

    @patch("data.loader.read_jeopardy_questions")
    def test_load_questions_jeopardy(self, mock_read_jeopardy):
        """Test loading questions for the 'jeopardy' dataset."""
        self.mock_config.get.side_effect = lambda key: {
            "JBOT_QUESTION_DATASET": "jeopardy",
            "JBOT_FINAL_JEOPARDY_SCORE_SUB": "2000",
        }.get(key)
        expected_path = os.path.join(self.project_root, "dummy_jeopardy")
        self.mock_config.get_dataset_path.return_value = expected_path

        expected_question = Question("Jeopardy Q", "Jeopardy A", "Test", 100)
        mock_read_jeopardy.return_value = [expected_question]

        questions = load_questions(self.mock_config)

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0], expected_question)

        self.mock_config.get_dataset_path.assert_called_once_with("jeopardy")
        mock_read_jeopardy.assert_called_once_with(
            expected_path, "2000", allowed_clue_values=[100, 200]
        )

    @patch("data.loader.read_knowledge_bowl_questions")
    def test_load_questions_knowledge_bowl(self, mock_read_kb):
        """Test loading questions for the 'knowledge_bowl' dataset."""
        self.mock_config.get.side_effect = lambda key: {
            "JBOT_QUESTION_DATASET": "knowledge_bowl",
        }.get(key)
        expected_path = os.path.join(self.project_root, "dummy_knowledge_bowl")
        self.mock_config.get_dataset_path.return_value = expected_path

        expected_question = Question("KB Q", "KB A", "Test", 10)
        mock_read_kb.return_value = [expected_question]

        questions = load_questions(self.mock_config)

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0], expected_question)

        self.mock_config.get_dataset_path.assert_called_once_with("knowledge_bowl")
        mock_read_kb.assert_called_once_with(expected_path)

    @patch("data.loader.read_riddle_questions")
    def test_load_questions_riddles_small(self, mock_read_riddles):
        """Test loading questions for the 'riddles_small' dataset."""
        self.mock_config.get.side_effect = lambda key: {
            "JBOT_QUESTION_DATASET": "riddles_small",
        }.get(key)
        expected_path = os.path.join(self.project_root, "dummy_riddles_small")
        self.mock_config.get_dataset_path.return_value = expected_path

        expected_question = Question("Riddle Q", "Riddle A", "Riddle", 100)
        mock_read_riddles.return_value = [expected_question]

        questions = load_questions(self.mock_config)

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0], expected_question)

        self.mock_config.get_dataset_path.assert_called_once_with("riddles_small")
        mock_read_riddles.assert_called_once_with(expected_path)

    @patch("data.loader.read_riddle_with_hints_questions")
    def test_load_questions_riddles_with_hints(self, mock_read_riddles_hints):
        """Test loading questions for the 'riddles_with_hints' dataset."""
        self.mock_config.get.side_effect = lambda key: {
            "JBOT_QUESTION_DATASET": "riddles_with_hints",
        }.get(key)
        expected_path = os.path.join(self.project_root, "dummy_riddles_with_hints")
        self.mock_config.get_dataset_path.return_value = expected_path

        expected_question = Question(
            "Riddle Hint Q", "Riddle Hint A", "Riddle", 100, hint="A hint"
        )
        mock_read_riddles_hints.return_value = [expected_question]

        questions = load_questions(self.mock_config)

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0], expected_question)

        self.mock_config.get_dataset_path.assert_called_once_with("riddles_with_hints")
        mock_read_riddles_hints.assert_called_once_with(expected_path)

    @patch("logging.info")
    @patch("logging.error")
    def test_load_questions_unknown_dataset(self, mock_log_error, mock_log_info):
        """Test loading questions with an unknown dataset."""
        self.mock_config.get.side_effect = lambda key: {
            "JBOT_QUESTION_DATASET": "unknown_dataset"
        }.get(key)

        questions = load_questions(self.mock_config)

        self.assertEqual(len(questions), 0)
        mock_log_info.assert_any_call(
            "Reading 'unknown_dataset' questions from file..."
        )
        mock_log_error.assert_any_call("Unknown dataset: unknown_dataset")

    @patch("data.loader.read_simple_questions")
    def test_load_questions_5th_grader(self, mock_read_simple):
        """Test loading questions for the '5th_grader' dataset."""
        self.mock_config.get.side_effect = lambda key: {
            "JBOT_QUESTION_DATASET": "5th_grader",
        }.get(key)
        expected_path = os.path.join(self.project_root, "dummy_5th_grader")
        self.mock_config.get_dataset_path.return_value = expected_path

        expected_question = Question(
            "5th Q", "5th A", "Are You Smarter Than a Fifth Grader", 100
        )
        mock_read_simple.return_value = [expected_question]

        questions = load_questions(self.mock_config)

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0], expected_question)

        self.mock_config.get_dataset_path.assert_called_once_with("5th_grader")
        mock_read_simple.assert_called_once_with(
            expected_path, "Are You Smarter Than a Fifth Grader"
        )

    @patch("data.loader.read_general_trivia_questions")
    def test_load_questions_general_trivia(self, mock_read_general):
        """Test loading questions for the 'general_trivia' dataset."""
        self.mock_config.get.side_effect = lambda key: {
            "JBOT_QUESTION_DATASET": "general_trivia",
        }.get(key)
        expected_path = os.path.join(self.project_root, "dummy_general_trivia")
        self.mock_config.get_dataset_path.return_value = expected_path

        expected_question = Question("General Q", "General A", "Trivia", 100)
        mock_read_general.return_value = [expected_question]

        questions = load_questions(self.mock_config)

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0], expected_question)

        self.mock_config.get_dataset_path.assert_called_once_with("general_trivia")
        mock_read_general.assert_called_once_with(expected_path)

    @patch("data.loader.read_simple_questions")
    def test_load_questions_millionaire_easy(self, mock_read_simple):
        """Test loading questions for the 'millionaire_easy' dataset."""
        self.mock_config.get.side_effect = lambda key: {
            "JBOT_QUESTION_DATASET": "millionaire_easy",
        }.get(key)
        expected_path = os.path.join(self.project_root, "dummy_millionaire_easy")
        self.mock_config.get_dataset_path.return_value = expected_path

        expected_question = Question(
            "Mill Easy Q", "Mill Easy A", "Millionaire (Easy)", 100
        )
        mock_read_simple.return_value = [expected_question]

        questions = load_questions(self.mock_config)

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0], expected_question)

        self.mock_config.get_dataset_path.assert_called_once_with("millionaire_easy")
        mock_read_simple.assert_called_once_with(expected_path, "Millionaire (Easy)")

    @patch("data.loader.read_simple_questions")
    def test_load_questions_millionaire_hard(self, mock_read_simple):
        """Test loading questions for the 'millionaire_hard' dataset."""
        self.mock_config.get.side_effect = lambda key: {
            "JBOT_QUESTION_DATASET": "millionaire_hard",
        }.get(key)
        expected_path = os.path.join(self.project_root, "dummy_millionaire_hard")
        self.mock_config.get_dataset_path.return_value = expected_path

        expected_question = Question(
            "Mill Hard Q", "Mill Hard A", "Millionaire (Hard)", 100
        )
        mock_read_simple.return_value = [expected_question]

        questions = load_questions(self.mock_config)

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0], expected_question)

        self.mock_config.get_dataset_path.assert_called_once_with("millionaire_hard")
        mock_read_simple.assert_called_once_with(expected_path, "Millionaire (Hard)")


if __name__ == "__main__":
    unittest.main()
