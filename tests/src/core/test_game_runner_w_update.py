import unittest
from unittest.mock import MagicMock, patch, ANY
import os
import sys

# Add the project root to the Python path
project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
sys.path.insert(0, project_root)

from src.core.game_runner import GameRunner
from src.core.player_manager import PlayerManager
from db.database import Database
from data.readers.question import Question


class TestGameRunnerResetQuestion(unittest.TestCase):
    def setUp(self):
        # Patch ConfigReader
        self.config_patcher = patch("src.core.game_runner.ConfigReader")
        self.MockConfigReader = self.config_patcher.start()
        self.addCleanup(self.config_patcher.stop)

        # Defaults
        self.mock_config_instance = self.MockConfigReader.return_value
        self.defaults = {
            "JBOT_RIDDLE_HISTORY_DAYS": "30",
            "JBOT_QUESTION_RETRIES": "10",
            "JBOT_EMOJI_FASTEST": "🥇",
        }
        self.mock_config_instance.get.side_effect = lambda k, d=None: self.defaults.get(
            k, d
        )
        self.mock_config_instance.get_bool.side_effect = lambda k, d=False: (
            str(self.defaults.get(k)).lower() == "true" if k in self.defaults else d
        )

        self.mock_question_selector = MagicMock()
        self.mock_data_manager = MagicMock()
        self.game_runner = GameRunner(
            self.mock_question_selector, self.mock_data_manager
        )

    def test_reset_daily_question_success(self):
        # Arrange
        initial_question = Question("q1", "a1", "c1", 100, "s1", "h1")
        new_question = Question("q2", "a2", "c2", 200, "s2", "h2")
        self.game_runner.daily_q = initial_question
        self.game_runner.daily_question_id = 1

        self.mock_data_manager.get_used_question_hashes.return_value = {"old_hash"}
        self.mock_question_selector.get_random_question.return_value = new_question
        self.mock_data_manager.log_daily_question.return_value = 2

        # Act
        result = self.game_runner.reset_daily_question()

        # Assert
        self.assertTrue(result)
        self.mock_data_manager.get_used_question_hashes.assert_called_once()
        self.mock_question_selector.get_random_question.assert_called_once_with(
            exclude_hashes={"old_hash"}, previous_answers=ANY
        )
        self.mock_data_manager.log_daily_question.assert_called_once_with(
            new_question, force_new=True
        )
        self.assertEqual(self.game_runner.daily_q, new_question)
        self.assertEqual(self.game_runner.daily_question_id, 2)

    def test_reset_daily_question_failure_on_log(self):
        # Arrange
        initial_question = Question("q1", "a1", "c1", 100, "s1", "h1")
        new_question = Question("q2", "a2", "c2", 200, "s2", "h2")
        self.game_runner.daily_q = initial_question
        self.game_runner.daily_question_id = 1

        self.mock_data_manager.get_used_question_hashes.return_value = set()
        self.mock_question_selector.get_random_question.return_value = new_question
        self.mock_data_manager.log_daily_question.return_value = None

        # Act
        result = self.game_runner.reset_daily_question()

        # Assert
        self.assertFalse(result)
        self.assertEqual(self.game_runner.daily_q, new_question)  # Still updated
        self.assertIsNone(self.game_runner.daily_question_id)


if __name__ == "__main__":
    unittest.main()
