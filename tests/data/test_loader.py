import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add the project root to the Python path to allow for absolute imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)

from data.loader import load_questions
from data.readers.question import Question
from src.cfg.main import ConfigReader

class TestLoadQuestions(unittest.TestCase):

    def setUp(self):
        """Set up a mock ConfigReader for testing."""
        self.mock_config = MagicMock(spec=ConfigReader)
        # Define a dummy project root for the loader to use
        self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

        # Mock the config get method to return dummy paths
        self.mock_config.get.side_effect = lambda key: {
            "JBOT_QUESTION_DATASET": "jeopardy",
            "JBOT_JEOPARDY_LOCAL_PATH": "dummy_jeopardy.tsv",
            "JBOT_KNOWLEDGE_BOWL_LOCAL_PATH": "dummy_kb.tsv",
            "JBOT_RIDDLE_SMALL_LOCAL_PATH": "dummy_riddles.csv",
            "JBOT_RIDDLE_HINTS_LOCAL_PATH": "dummy_riddles_hints.csv",
            "JBOT_FINAL_JEOPARDY_SCORE_SUB": "2000"
        }.get(key)

    @patch('data.loader.read_jeopardy_questions')
    def test_load_questions_jeopardy(self, mock_read_jeopardy):
        """Test loading questions for the 'jeopardy' dataset."""
        self.mock_config.get.side_effect = lambda key: {
            "JBOT_QUESTION_DATASET": "jeopardy",
            "JBOT_JEOPARDY_LOCAL_PATH": "dummy_jeopardy.tsv",
            "JBOT_FINAL_JEOPARDY_SCORE_SUB": "2000"
        }.get(key)
        
        expected_question = Question("Jeopardy Q", "Jeopardy A", "Test", 100)
        mock_read_jeopardy.return_value = [expected_question]

        questions = load_questions(self.mock_config)

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0], expected_question)
        
        expected_path = os.path.join(self.project_root, "dummy_jeopardy.tsv")
        mock_read_jeopardy.assert_called_once_with(expected_path, "2000")

    @patch('data.loader.read_knowledge_bowl_questions')
    def test_load_questions_knowledge_bowl(self, mock_read_kb):
        """Test loading questions for the 'knowledge_bowl' dataset."""
        self.mock_config.get.side_effect = lambda key: {
            "JBOT_QUESTION_DATASET": "knowledge_bowl",
            "JBOT_KNOWLEDGE_BOWL_LOCAL_PATH": "dummy_kb.tsv"
        }.get(key)

        expected_question = Question("KB Q", "KB A", "Test", 10)
        mock_read_kb.return_value = [expected_question]

        questions = load_questions(self.mock_config)

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0], expected_question)
        
        expected_path = os.path.join(self.project_root, "dummy_kb.tsv")
        mock_read_kb.assert_called_once_with(expected_path)

    @patch('data.loader.read_riddle_questions')
    def test_load_questions_riddles_small(self, mock_read_riddles):
        """Test loading questions for the 'riddles_small' dataset."""
        self.mock_config.get.side_effect = lambda key: {
            "JBOT_QUESTION_DATASET": "riddles_small",
            "JBOT_RIDDLE_SMALL_LOCAL_PATH": "dummy_riddles.csv"
        }.get(key)

        expected_question = Question("Riddle Q", "Riddle A", "Riddle", 100)
        mock_read_riddles.return_value = [expected_question]

        questions = load_questions(self.mock_config)

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0], expected_question)
        
        expected_path = os.path.join(self.project_root, "dummy_riddles.csv")
        mock_read_riddles.assert_called_once_with(expected_path)

    @patch('data.loader.read_riddle_with_hints_questions')
    def test_load_questions_riddles_with_hints(self, mock_read_riddles_hints):
        """Test loading questions for the 'riddles_with_hints' dataset."""
        self.mock_config.get.side_effect = lambda key: {
            "JBOT_QUESTION_DATASET": "riddles_with_hints",
            "JBOT_RIDDLE_HINTS_LOCAL_PATH": "dummy_riddles_hints.csv"
        }.get(key)

        expected_question = Question("Riddle Hint Q", "Riddle Hint A", "Riddle", 100, hint="A hint")
        mock_read_riddles_hints.return_value = [expected_question]

        questions = load_questions(self.mock_config)

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0], expected_question)
        
        expected_path = os.path.join(self.project_root, "dummy_riddles_hints.csv")
        mock_read_riddles_hints.assert_called_once_with(expected_path)

    @patch('builtins.print')
    def test_load_questions_unknown_dataset(self, mock_print):
        """Test loading questions with an unknown dataset."""
        self.mock_config.get.side_effect = lambda key: {"JBOT_QUESTION_DATASET": "unknown_dataset"}.get(key)

        questions = load_questions(self.mock_config)

        self.assertEqual(len(questions), 0)
        mock_print.assert_any_call("Reading 'unknown_dataset' questions from file...")
        mock_print.assert_any_call("Unknown dataset: unknown_dataset")

if __name__ == '__main__':
    unittest.main()
