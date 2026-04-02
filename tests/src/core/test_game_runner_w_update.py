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
            "JBOT_EMOJI_FASTEST_CSV": "🥇,🥈,🥉",
            "JBOT_BONUS_FASTEST_CSV": "10,5,1",
            "JBOT_BONUS_TRY_CSV": "20,10,5",
            "JBOT_BONUS_BEFORE_HINT": "10",
            "JBOT_BONUS_STREAK_PER_DAY": "5",
            "JBOT_BONUS_STREAK_CAP": "25",
            "JBOT_EMOJI_FIRST_TRY": "🎯",
            "JBOT_EMOJI_BEFORE_HINT": "🧠",
            "JBOT_EMOJI_STREAK": "🔥",
            "JBOT_EMOJI_STREAK_BROKEN": "💔",
            "JBOT_EMOJI_JINXED": "🥶",
            "JBOT_EMOJI_SILENCED": "🤐",
            "JBOT_EMOJI_STOLEN_FROM": "💸",
            "JBOT_EMOJI_STEALING": "💰",
            "JBOT_EMOJI_REST": "😴",
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
        self.mock_data_manager.get_todays_daily_question.return_value = (
            new_question,
            2,
            2,
        )

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
        self.mock_data_manager.get_todays_daily_question.return_value = None

        # Act
        result = self.game_runner.reset_daily_question()

        # Assert
        self.assertFalse(result)
        self.assertEqual(self.game_runner.daily_q, new_question)  # Still updated
        self.assertIsNone(self.game_runner.daily_question_id)

    def test_reset_clears_stale_powerup_state(self):
        """After a skip, daily powerup state from the old question is cleared."""
        new_question = Question("q2", "a2", "c2", 200, "s2", "h2")
        self.game_runner.daily_q = Question("q1", "a1", "c1", 100, "s1", "h1")
        self.game_runner.daily_question_id = 1

        self.mock_data_manager.get_used_question_hashes.return_value = set()
        self.mock_question_selector.get_random_question.return_value = new_question
        self.mock_data_manager.log_daily_question.return_value = 2
        self.mock_data_manager.get_todays_daily_question.return_value = (
            new_question,
            2,
            2,
        )

        mock_powerup = MagicMock()
        self.game_runner.managers["powerup"] = mock_powerup

        self.game_runner.reset_daily_question()

        mock_powerup.reset_daily_state.assert_called_once()

    def test_reset_hydrates_powerups_with_new_question_id(self):
        """After a skip, overnight pre-loads are hydrated for the new question ID."""
        new_question = Question("q2", "a2", "c2", 200, "s2", "h2")
        self.game_runner.daily_q = Question("q1", "a1", "c1", 100, "s1", "h1")
        self.game_runner.daily_question_id = 1

        self.mock_data_manager.get_used_question_hashes.return_value = set()
        self.mock_question_selector.get_random_question.return_value = new_question
        self.mock_data_manager.log_daily_question.return_value = 2
        self.mock_data_manager.get_todays_daily_question.return_value = (
            new_question,
            2,
            2,
        )

        mock_powerup = MagicMock()
        self.game_runner.managers["powerup"] = mock_powerup

        self.game_runner.reset_daily_question()

        mock_powerup.hydrate_pending_powerups.assert_called_once_with(2)

    def test_reset_does_not_restore_game_state(self):
        """After a skip, restore_game_state is NOT called — prior answers stay out."""
        new_question = Question("q2", "a2", "c2", 200, "s2", "h2")
        self.game_runner.daily_q = Question("q1", "a1", "c1", 100, "s1", "h1")
        self.game_runner.daily_question_id = 1

        self.mock_data_manager.get_used_question_hashes.return_value = set()
        self.mock_question_selector.get_random_question.return_value = new_question
        self.mock_data_manager.log_daily_question.return_value = 2
        self.mock_data_manager.get_todays_daily_question.return_value = (
            new_question,
            2,
            2,
        )

        with patch.object(self.game_runner, "restore_game_state") as mock_restore:
            self.game_runner.reset_daily_question()
            mock_restore.assert_not_called()

    def test_reset_attempts_hint_generation(self):
        """After a skip, hint generation is called for the new question."""
        new_question = Question("q2", "a2", "c2", 200, "s2", "h2")
        self.game_runner.daily_q = Question("q1", "a1", "c1", 100, "s1", "h1")
        self.game_runner.daily_question_id = 1

        self.mock_data_manager.get_used_question_hashes.return_value = set()
        self.mock_question_selector.get_random_question.return_value = new_question
        self.mock_question_selector.get_hint_from_gemini.return_value = "new hint"
        self.mock_data_manager.log_daily_question.return_value = 2
        self.mock_data_manager.get_todays_daily_question.return_value = (
            new_question,
            2,
            2,
        )

        self.game_runner.reset_daily_question()

        self.mock_question_selector.get_hint_from_gemini.assert_called_once_with(
            new_question
        )
        self.assertEqual(new_question.hint, "new hint")


if __name__ == "__main__":
    unittest.main()
