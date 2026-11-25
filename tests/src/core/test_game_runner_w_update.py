import unittest
from unittest.mock import MagicMock, patch, ANY
import os
import sys

# Add the project root to the Python path
project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
sys.path.insert(0, project_root)

from src.core.data_manager import DataManager
from src.core.game_runner import GameRunner
from src.core.player_manager import PlayerManager
from src.core.state import DailyPlayerState
from db.database import Database
from data.readers.question import Question


class TestGameRunnerResetQuestion(unittest.TestCase):
    def setUp(self):
        # ConfigReader is an external boundary (reads .env), so it stays mocked.
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

        self.db = Database(":memory:")
        self.addCleanup(self.db.close)
        self.data_manager = DataManager(self.db)
        self.player_manager = PlayerManager(self.data_manager)
        for player_id, name in (("thief", "Thief"), ("target", "Target")):
            self.data_manager.create_player(player_id, name)

        # The question selector wraps the dataset readers and Gemini.
        self.mock_question_selector = MagicMock()
        self.mock_question_selector.get_hint_from_gemini.return_value = None
        self.game_runner = GameRunner(
            self.mock_question_selector,
            self.data_manager,
            player_manager=self.player_manager,
        )

        self.initial_question = Question("q1", "a1", "c1", 100, "s1", "h1")
        self.new_question = Question("q2", "a2", "c2", 200, "s2", "h2")
        self.initial_id = self.data_manager.log_daily_question(self.initial_question)
        self.game_runner.daily_q = self.initial_question
        self.game_runner.daily_question_id = self.initial_id
        self.mock_question_selector.get_random_question.return_value = self.new_question

    def _daily_question_ids(self) -> list[int]:
        rows = self.db.execute_query("SELECT id FROM daily_questions ORDER BY id")
        return [row["id"] for row in rows]

    def test_reset_daily_question_success(self):
        result = self.game_runner.reset_daily_question()

        self.assertTrue(result)
        self.mock_question_selector.get_random_question.assert_called_once_with(
            exclude_hashes={str(self.initial_question.id)}, previous_answers=ANY
        )
        new_id = self.data_manager.get_todays_daily_question()[1]
        self.assertEqual(self._daily_question_ids(), [self.initial_id, new_id])
        self.assertNotEqual(new_id, self.initial_id)
        self.assertEqual(self.game_runner.daily_q.answer, "a2")
        self.assertEqual(self.game_runner.daily_question_id, new_id)

    def test_reset_daily_question_failure_on_log(self):
        # Simulates the DB failing to record the replacement question.
        with patch.object(
            self.data_manager, "log_daily_question", return_value=None
        ), patch.object(
            self.data_manager, "get_todays_daily_question", return_value=None
        ):
            result = self.game_runner.reset_daily_question()

        self.assertFalse(result)
        self.assertEqual(self.game_runner.daily_q, self.initial_question)
        self.assertEqual(self.game_runner.daily_question_id, self.initial_id)
        self.assertEqual(self._daily_question_ids(), [self.initial_id])

    def test_reset_clears_stale_powerup_state(self):
        """After a skip, daily powerup state from the old question is cleared."""
        powerup = self.game_runner.managers["powerup"]
        powerup.daily_state["thief"] = DailyPlayerState(is_resting=True)

        self.game_runner.reset_daily_question()

        self.assertNotIn("thief", powerup.daily_state)

    def test_reset_hydrates_powerups_with_new_question_id(self):
        """After a skip, overnight pre-loads are hydrated for the new question ID."""
        self.data_manager.log_powerup_usage("thief", "jinx_preload", "target", None)
        powerup = self.game_runner.managers["powerup"]
        powerup.hydrate_pending_powerups(self.initial_id)

        self.game_runner.reset_daily_question()

        new_id = self.game_runner.daily_question_id
        rows = self.data_manager.get_powerup_usages_for_question(new_id)
        self.assertEqual(
            [(r["user_id"], r["powerup_type"], r["target_user_id"]) for r in rows],
            [("thief", "jinx_preload", "target")],
        )
        self.assertEqual(
            self.data_manager.get_powerup_usages_for_question(self.initial_id), []
        )
        self.assertTrue(powerup.daily_state["thief"].silenced)
        self.assertEqual(powerup.daily_state["thief"].jinx_target, "target")

    def test_reset_does_not_restore_game_state(self):
        """After a skip, restore_game_state is NOT called — prior answers stay out."""
        self.data_manager.log_player_guess(
            "thief", "Thief", self.initial_id, "a1", True
        )

        with patch.object(self.game_runner, "restore_game_state") as mock_restore:
            self.game_runner.reset_daily_question()
            mock_restore.assert_not_called()

        powerup = self.game_runner.managers["powerup"]
        self.assertFalse(
            any(state.is_correct for state in powerup.daily_state.values())
        )

    def test_reset_attempts_hint_generation(self):
        """After a skip, hint generation is called for the new question."""
        self.mock_question_selector.get_hint_from_gemini.return_value = "new hint"

        self.game_runner.reset_daily_question()

        self.mock_question_selector.get_hint_from_gemini.assert_called_once_with(
            self.new_question
        )
        self.assertEqual(self.game_runner.daily_q.hint, "new hint")
        stored = self.db.execute_query(
            "SELECT hint_text FROM questions WHERE answer_text = 'a2'"
        )
        self.assertEqual(stored[0]["hint_text"], "new hint")


if __name__ == "__main__":
    unittest.main()
