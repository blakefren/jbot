import unittest
from unittest.mock import MagicMock
from src.core.game_runner import GameRunner
from src.core.data_manager import DataManager
from data.readers.question import Question


class TestGameRunnerPowerupBadges(unittest.TestCase):
    def setUp(self):
        self.mock_qs = MagicMock()
        self.mock_dm = MagicMock(spec=DataManager)
        self.runner = GameRunner(self.mock_qs, self.mock_dm)
        self.runner.daily_question_id = 123

        # Mock config to ensure emojis are what we expect
        self.runner.config = MagicMock()
        self.defaults = {
            "JBOT_EMOJI_JINXED": "🥶",
            "JBOT_EMOJI_SILENCED": "🤐",
            "JBOT_EMOJI_STOLEN_FROM": "💸",
            "JBOT_EMOJI_STEALING": "💰",
            "JBOT_EMOJI_SHIELD": "💝",
            "JBOT_EMOJI_SHIELD_BROKEN": "💔",
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
        }
        self.runner.config.get.side_effect = (
            lambda key, default=None: self.defaults.get(key)
        )

        # Setup basic player scores
        self.mock_dm.get_player_scores.return_value = [
            {"id": "p1", "name": "Player1", "score": 100},
            {"id": "p2", "name": "Player2", "score": 90},
            {"id": "p3", "name": "Player3", "score": 80},
        ]
        self.mock_dm.get_player_streaks.return_value = []

        # Mock daily bonus helpers to return empty/None
        self.mock_dm.read_guess_history.return_value = []
        self.mock_dm.get_hint_sent_timestamp.return_value = None
        self.mock_dm.get_first_try_solvers.return_value = []

    def test_leaderboard_jinx_badges(self):
        # p1 jinxed p2 - both answered correctly
        self.mock_dm.get_powerup_usages_for_question.return_value = [
            {"powerup_type": "jinx", "user_id": "p1", "target_user_id": "p2"}
        ]
        # Mock that both players answered correctly today
        self.mock_dm.read_guess_history.return_value = [
            {
                "daily_question_id": 123,
                "player_id": "p1",
                "is_correct": True,
                "guessed_at": "2024-01-01 10:00:00",
            },
            {
                "daily_question_id": 123,
                "player_id": "p2",
                "is_correct": True,
                "guessed_at": "2024-01-01 10:05:00",
            },
        ]

        leaderboard = self.runner.get_scores_leaderboard(show_daily_bonuses=True)

        # p1 should have silenced emoji (attacker)
        self.assertIn("Player1", leaderboard)
        self.assertIn("🤐", leaderboard)  # p1 badge

        # p2 should have jinxed emoji (victim)
        self.assertIn("Player2", leaderboard)
        self.assertIn("🥶", leaderboard)  # p2 badge

    def test_leaderboard_steal_badges(self):
        # p1 stole from p2 - both answered correctly
        self.mock_dm.get_powerup_usages_for_question.return_value = [
            {"powerup_type": "steal", "user_id": "p1", "target_user_id": "p2"}
        ]
        # Mock that both players answered correctly today
        self.mock_dm.read_guess_history.return_value = [
            {
                "daily_question_id": 123,
                "player_id": "p1",
                "is_correct": True,
                "guessed_at": "2024-01-01 10:00:00",
            },
            {
                "daily_question_id": 123,
                "player_id": "p2",
                "is_correct": True,
                "guessed_at": "2024-01-01 10:05:00",
            },
        ]

        leaderboard = self.runner.get_scores_leaderboard(show_daily_bonuses=True)

        # p1 should have stealing emoji
        self.assertIn("💰", leaderboard)

        # p2 should have stolen from emoji
        self.assertIn("💸", leaderboard)

    def test_leaderboard_steal_badge_attacker_did_not_answer(self):
        """Steal badge should appear for attacker even if they never answered that day."""
        # p1 stole from p2, but p1 never guessed
        self.mock_dm.get_powerup_usages_for_question.return_value = [
            {"powerup_type": "steal", "user_id": "p1", "target_user_id": "p2"}
        ]
        # Only p2 answered correctly today; p1 did not answer at all
        self.mock_dm.read_guess_history.return_value = [
            {
                "daily_question_id": 123,
                "player_id": "p2",
                "is_correct": True,
                "guessed_at": "2024-01-01 10:05:00",
            },
        ]

        leaderboard = self.runner.get_scores_leaderboard(show_daily_bonuses=True)

        # p1 should still have the stealing emoji
        lines = leaderboard.split("\n")
        p1_line = next((line for line in lines if "Player1" in line), None)
        self.assertIsNotNone(p1_line, "Player1 should be in leaderboard")
        self.assertIn("💰", p1_line, "Attacker should show stealing badge even without answering")

        # p2 should have stolen_from emoji
        p2_line = next((line for line in lines if "Player2" in line), None)
        self.assertIsNotNone(p2_line, "Player2 should be in leaderboard")
        self.assertIn("💸", p2_line)

    def test_leaderboard_shield_badge(self):
        # p1 used shield
        self.mock_dm.get_powerup_usages_for_question.return_value = [
            {"powerup_type": "shield", "user_id": "p1", "target_user_id": None}
        ]

        leaderboard = self.runner.get_scores_leaderboard(show_daily_bonuses=True)

        # p1 should have shield emoji
        self.assertIn("💝", leaderboard)

    def test_leaderboard_no_badges_if_not_show_daily_bonuses(self):
        # p1 used shield
        self.mock_dm.get_powerup_usages_for_question.return_value = [
            {"powerup_type": "shield", "user_id": "p1", "target_user_id": None}
        ]

        leaderboard = self.runner.get_scores_leaderboard(show_daily_bonuses=False)

        # Should NOT have shield emoji
        self.assertNotIn("💝", leaderboard)

    def test_leaderboard_duplicate_steal_blocked(self):
        """Test that when a second steal attempt is blocked, the target doesn't get duplicate badges."""
        # Only p1's steal was successful - p2's was blocked
        # Database should only have one steal record for target p3
        self.mock_dm.get_powerup_usages_for_question.return_value = [
            {"powerup_type": "steal", "user_id": "p1", "target_user_id": "p3"}
        ]
        # Mock that all players answered correctly today
        self.mock_dm.read_guess_history.return_value = [
            {
                "daily_question_id": 123,
                "player_id": "p1",
                "is_correct": True,
                "guessed_at": "2024-01-01 10:00:00",
            },
            {
                "daily_question_id": 123,
                "player_id": "p2",
                "is_correct": True,
                "guessed_at": "2024-01-01 10:01:00",
            },
            {
                "daily_question_id": 123,
                "player_id": "p3",
                "is_correct": True,
                "guessed_at": "2024-01-01 10:02:00",
            },
        ]

        leaderboard = self.runner.get_scores_leaderboard(show_daily_bonuses=True)

        # p3 should have stolen from emoji exactly once
        # Count occurrences of the emoji in p3's line
        lines = leaderboard.split("\n")
        p3_line = next((line for line in lines if "Player3" in line), None)
        self.assertIsNotNone(p3_line, "Player3 should be in leaderboard")

        # Count the number of 💸 emojis in p3's line - should be exactly 1
        stolen_from_count = p3_line.count("💸")
        self.assertEqual(
            stolen_from_count,
            1,
            f"Expected exactly 1 💸 badge, found {stolen_from_count}",
        )
