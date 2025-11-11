import unittest
from unittest.mock import MagicMock, patch
import os
import sys

# Add the project root to the Python path
project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
sys.path.insert(0, project_root)

from src.core.game_runner import GameRunner
from src.cfg.players import PlayerManager
from db.database import Database
from data.readers.question import Question


class TestGameRunnerUpdateScores(unittest.TestCase):
    def setUp(self):
        """Set up a mock environment for testing."""
        self.mock_db = MagicMock(spec=Database)
        self.mock_data_manager = MagicMock()
        self.mock_data_manager.db = self.mock_db

        self.mock_question_selector = MagicMock()

        # Patch PlayerManager to use the mock DB
        with patch(
            "src.core.game_runner.PlayerManager", autospec=True
        ) as mock_player_manager_class:
            self.mock_player_manager = mock_player_manager_class.return_value
            self.game_runner = GameRunner(
                self.mock_question_selector, self.mock_data_manager
            )
            self.game_runner.player_manager = self.mock_player_manager

    def test_update_scores_calls_save_players(self):
        """Test that update_scores calls player_manager.save_players."""
        # Act
        self.game_runner.daily_question_id = 1
        self.game_runner.update_scores()

        # Assert
        self.mock_player_manager.save_players.assert_called_once()


class TestGameRunnerResetQuestion(unittest.TestCase):
    def setUp(self):
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

        self.mock_question_selector.get_question_for_today.return_value = new_question
        self.mock_data_manager.log_daily_question.return_value = 2

        # Act
        result = self.game_runner.reset_daily_question()

        # Assert
        self.assertTrue(result)
        self.mock_question_selector.get_question_for_today.assert_called_once()
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

        self.mock_question_selector.get_question_for_today.return_value = new_question
        self.mock_data_manager.log_daily_question.return_value = None

        # Act
        result = self.game_runner.reset_daily_question()

        # Assert
        self.assertFalse(result)
        self.assertEqual(self.game_runner.daily_q, new_question)  # Still updated
        self.assertIsNone(self.game_runner.daily_question_id)


if __name__ == "__main__":
    unittest.main()
