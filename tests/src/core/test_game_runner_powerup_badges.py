import unittest
from unittest.mock import MagicMock, patch

from data.readers.question import Question
from db.database import Database
from src.core.data_manager import DataManager
from src.core.game_runner import GameRunner
from src.core.player_manager import PlayerManager


class TestGameRunnerPowerupBadges(unittest.TestCase):
    def setUp(self):
        self.config = MagicMock()
        self.defaults = {
            "JBOT_EMOJI_JINXED": "🥶",
            "JBOT_EMOJI_SILENCED": "🤐",
            "JBOT_EMOJI_STOLEN_FROM": "💸",
            "JBOT_EMOJI_STEALING": "💰",
            "JBOT_EMOJI_REST": "😴",
            "JBOT_EMOJI_STREAK": "🔥",
            "JBOT_EMOJI_FASTEST": "🥇",
            "JBOT_EMOJI_FIRST_TRY": "🎯",
            "JBOT_EMOJI_BEFORE_HINT": "🧠",
            "JBOT_BONUS_TRY_CSV": "20,10,5",
            "JBOT_BONUS_FASTEST_CSV": "10,5,5",
            "JBOT_BONUS_BEFORE_HINT": "10",
            "JBOT_BONUS_STREAK_PER_DAY": "5",
            "JBOT_BONUS_STREAK_CAP": "25",
            "JBOT_EMOJI_FASTEST_CSV": "🥇,🥈,🥉",
            "JBOT_FIRST_PLACE_ROLE_NAME": "",
        }
        self.config.get.side_effect = lambda key, default=None: self.defaults.get(
            key, default
        )
        self.config.is_seasons_enabled.return_value = False
        self.db = Database(":memory:")
        self.data_manager = DataManager(self.db)
        self.player_manager = PlayerManager(self.data_manager)
        for player_id, name, score in (
            ("p1", "Player1", 100),
            ("p2", "Player2", 90),
            ("p3", "Player3", 80),
        ):
            self.player_manager.get_or_create_player(player_id, name)
            self.player_manager.update_score(player_id, score)
        self.daily_question_id = self.data_manager.log_daily_question(
            Question("Question", "Answer", "Test", 100)
        )
        with patch("src.core.game_runner.ConfigReader", return_value=self.config):
            self.runner = GameRunner(
                MagicMock(), self.data_manager, player_manager=self.player_manager
            )
        self.runner.daily_question_id = self.daily_question_id

    def tearDown(self):
        self.db.close()

    def _guess(self, player_id, answer="Answer", correct=True):
        self.data_manager.log_player_guess(
            player_id, player_id, self.daily_question_id, answer, correct
        )

    def _powerup(self, powerup_type, user_id, target_id=None):
        self.data_manager.log_powerup_usage(
            user_id, powerup_type, target_id, self.daily_question_id
        )

    @staticmethod
    def _player_line(leaderboard, player_name):
        return next(line for line in leaderboard.splitlines() if player_name in line)

    def test_leaderboard_jinx_badges(self):
        self._powerup("jinx", "p1", "p2")
        self._guess("p1")
        self._guess("p2")

        leaderboard = self.runner.get_scores_leaderboard(show_daily_bonuses=True)

        self.assertIn("🤐", self._player_line(leaderboard, "Player1"))
        self.assertIn("🥶", self._player_line(leaderboard, "Player2"))

    def test_leaderboard_steal_badges(self):
        self._powerup("steal", "p1", "p2")
        self._guess("p1")
        self._guess("p2")

        leaderboard = self.runner.get_scores_leaderboard(show_daily_bonuses=True)

        self.assertIn("💰", self._player_line(leaderboard, "Player1"))
        self.assertIn("💸", self._player_line(leaderboard, "Player2"))

    def test_leaderboard_steal_badge_attacker_did_not_answer(self):
        self._powerup("steal", "p1", "p2")
        self._guess("p2")

        leaderboard = self.runner.get_scores_leaderboard(show_daily_bonuses=True)

        self.assertIn("💰", self._player_line(leaderboard, "Player1"))
        self.assertIn("💸", self._player_line(leaderboard, "Player2"))

    def test_leaderboard_jinx_late_badge(self):
        self._powerup("jinx_late", "p1", "p2")
        self._guess("p1")
        self._guess("p2")

        leaderboard = self.runner.get_scores_leaderboard(show_daily_bonuses=True)

        self.assertIn("🤐", self._player_line(leaderboard, "Player1"))
        self.assertIn("🥶", self._player_line(leaderboard, "Player2"))

    def test_leaderboard_jinx_preload_badge(self):
        self._powerup("jinx_preload", "p1", "p2")
        self._guess("p1")
        self._guess("p2")

        leaderboard = self.runner.get_scores_leaderboard(show_daily_bonuses=True)

        self.assertIn("🤐", self._player_line(leaderboard, "Player1"))
        self.assertIn("🥶", self._player_line(leaderboard, "Player2"))

    def test_leaderboard_rest_badge(self):
        self._powerup("rest", "p1")

        leaderboard = self.runner.get_scores_leaderboard(show_daily_bonuses=True)

        self.assertIn("😴", self._player_line(leaderboard, "Player1"))

    def test_leaderboard_no_badges_if_not_show_daily_bonuses(self):
        self._powerup("rest", "p1")

        leaderboard = self.runner.get_scores_leaderboard(show_daily_bonuses=False)

        self.assertNotIn("😴", leaderboard)

    def test_leaderboard_duplicate_steal_blocked(self):
        self._powerup("steal", "p1", "p3")
        self._guess("p1")
        self._guess("p2")
        self._guess("p3")

        leaderboard = self.runner.get_scores_leaderboard(show_daily_bonuses=True)

        self.assertEqual(self._player_line(leaderboard, "Player3").count("💸"), 1)

    def test_same_second_correct_guesses_rank_by_insertion_order(self):
        today = self.data_manager.get_today()
        self._guess("p3")
        self._guess("p1")
        self.db.execute_update(
            "UPDATE guesses SET guessed_at = ? WHERE daily_question_id = ?",
            (f"{today} 10:00:00", self.daily_question_id),
        )

        leaderboard = self.runner.get_scores_leaderboard(show_daily_bonuses=True)

        self.assertIn("🥇", self._player_line(leaderboard, "Player3"))
        self.assertIn("🥈", self._player_line(leaderboard, "Player1"))

    def test_same_second_as_hint_counts_as_before_hint(self):
        today = self.data_manager.get_today()
        self.data_manager.log_messaging_event(
            "outgoing", "Discord", "c", "morning", "morning_message"
        )
        self.data_manager.log_messaging_event(
            "outgoing", "Discord", "c", "reminder", "reminder_message"
        )
        self.db.execute_update(
            "UPDATE messages SET timestamp = ? WHERE status = 'morning_message'",
            (f"{today} 08:00:00",),
        )
        self.db.execute_update(
            "UPDATE messages SET timestamp = ? WHERE status = 'reminder_message'",
            (f"{today} 12:00:00",),
        )
        self._guess("p1")
        self.db.execute_update(
            "UPDATE guesses SET guessed_at = ? WHERE daily_question_id = ?",
            (f"{today} 12:00:00", self.daily_question_id),
        )

        leaderboard = self.runner.get_scores_leaderboard(show_daily_bonuses=True)

        self.assertIn("🧠", self._player_line(leaderboard, "Player1"))


if __name__ == "__main__":
    unittest.main()
