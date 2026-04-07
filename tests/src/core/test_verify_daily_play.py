import unittest
from unittest.mock import MagicMock, patch
from src.core.game_runner import GameRunner
from src.core.player import Player
from data.readers.question import Question


class TestVerifyDailyPlay(unittest.TestCase):
    """Tests for GameRunner.verify_daily_play and format_verify_report."""

    def _make_player(self, pid, score, streak, season_score=0, name=None):
        return Player(
            id=pid,
            name=name or pid,
            score=score,
            answer_streak=streak,
            season_score=season_score,
        )

    def setUp(self):
        self.mock_question_selector = MagicMock()
        self.mock_data_manager = MagicMock()
        self.game_runner = GameRunner(
            self.mock_question_selector, self.mock_data_manager
        )

        self.question = Question(
            question="What is 2+2?", answer="4", category="Math", clue_value=100
        )

        # Config defaults matching scoring constants
        self.game_runner.config = MagicMock()
        defaults = {
            "JBOT_BONUS_TRY_CSV": "20,10,5",
            "JBOT_BONUS_FASTEST_CSV": "10,5,1",
            "JBOT_BONUS_BEFORE_HINT": "10",
            "JBOT_BONUS_STREAK_PER_DAY": "5",
            "JBOT_BONUS_STREAK_CAP": "25",
            "JBOT_EMOJI_FIRST_TRY": "🎯",
            "JBOT_EMOJI_BEFORE_HINT": "🧠",
            "JBOT_EMOJI_FASTEST": "🥇",
            "JBOT_EMOJI_FASTEST_CSV": "🥇,🥈,🥉",
            "JBOT_EMOJI_STREAK": "🔥",
            "JBOT_STEAL_STREAK_COST": "2",
            "JBOT_RETRO_STEAL_STREAK_COST": "4",
            "JBOT_RETRO_JINX_BONUS_RATIO": "0.5",
        }
        self.game_runner.config.get.side_effect = lambda k, d=None: defaults.get(k, d)

    def _setup_common_mocks(
        self, snapshot, guess_events, powerup_events, season_id=None
    ):
        """Helper to configure DataManager mocks for a verification run."""
        self.mock_data_manager.get_daily_snapshot.return_value = snapshot
        self.mock_data_manager.get_daily_question_by_id.return_value = (
            self.question,
            42,
        )
        self.mock_data_manager.get_alternative_answers.return_value = []
        self.mock_data_manager.get_hint_sent_timestamp.return_value = None
        self.mock_data_manager.get_guesses_for_daily_question.return_value = (
            guess_events
        )
        self.mock_data_manager.get_powerup_usages_for_question.return_value = (
            powerup_events
        )
        self.mock_data_manager.get_snapshot_season_id.return_value = season_id

    def test_no_snapshot_returns_empty(self):
        """When no snapshot exists, verify_daily_play returns []."""
        self.mock_data_manager.get_daily_snapshot.return_value = {}
        result = self.game_runner.verify_daily_play(1)
        self.assertEqual(result, [])

    def test_no_question_returns_empty(self):
        """When the question cannot be found, verify_daily_play returns []."""
        self.mock_data_manager.get_daily_snapshot.return_value = {
            "p1": self._make_player("p1", 100, 2)
        }
        self.mock_data_manager.get_daily_question_by_id.return_value = None
        result = self.game_runner.verify_daily_play(1)
        self.assertEqual(result, [])

    def test_scores_match_no_diffs(self):
        """When DB state matches simulator prediction, returns empty list."""
        # P1 had score=100 and streak=2 before today.
        # Today they answer correctly on first try → score_earned = 100+20+10+10 + streak bonus
        # streak_length = 3, streak_bonus = 3*5 = 15
        # total = 155; final_score = 255; final_streak = 3
        snapshot = {"p1": self._make_player("p1", 100, 2, name="Alice")}
        guesses = [
            {
                "player_id": "p1",
                "guess_text": "4",
                "is_correct": True,
                "guessed_at": "2024-01-15 10:00:00",
            }
        ]
        self._setup_common_mocks(snapshot, guesses, [])

        # DB state matches expected
        self.mock_data_manager.get_all_players.return_value = {
            "p1": self._make_player("p1", 255, 3)
        }

        result = self.game_runner.verify_daily_play(1)
        self.assertEqual(result, [])

    def test_score_mismatch_detected(self):
        """When the DB score doesn't match expected, a diff is returned."""
        snapshot = {"p1": self._make_player("p1", 100, 0, name="Alice")}
        guesses = [
            {
                "player_id": "p1",
                "guess_text": "4",
                "is_correct": True,
                "guessed_at": "2024-01-15 10:00:00",
            }
        ]
        self._setup_common_mocks(snapshot, guesses, [])

        # score_earned = 100 + 20 + 10 + 10 = 140 (base+first_try+before_hint+fastest)
        # But DB only has 100 + 50 = 150 (wrong)
        self.mock_data_manager.get_all_players.return_value = {
            "p1": self._make_player("p1", 150, 1)  # expected 240
        }

        result = self.game_runner.verify_daily_play(1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["player_id"], "p1")
        self.assertIn("score", result[0]["diffs"])
        self.assertEqual(result[0]["diffs"]["score"]["actual"], 150)

    def test_streak_mismatch_detected(self):
        """When the DB streak doesn't match expected, a diff is returned."""
        # P1 had streak=5; didn't answer today → streak should reset to 0.
        snapshot = {"p1": self._make_player("p1", 500, 5, name="Bob")}
        # No guesses → end_of_day resets streak
        self._setup_common_mocks(snapshot, [], [])

        # DB streak wasn't reset (bug scenario)
        self.mock_data_manager.get_all_players.return_value = {
            "p1": self._make_player("p1", 500, 5)  # should be 0
        }

        result = self.game_runner.verify_daily_play(1)
        self.assertEqual(len(result), 1)
        self.assertIn("streak", result[0]["diffs"])
        self.assertEqual(result[0]["diffs"]["streak"]["expected"], 0)
        self.assertEqual(result[0]["diffs"]["streak"]["actual"], 5)

    def test_season_score_mismatch_detected(self):
        """When the season score doesn't match, a diff is returned."""
        snapshot = {
            "p1": self._make_player("p1", 100, 0, season_score=50, name="Carol")
        }
        guesses = [
            {
                "player_id": "p1",
                "guess_text": "4",
                "is_correct": True,
                "guessed_at": "2024-01-15 10:00:00",
            }
        ]
        self._setup_common_mocks(snapshot, guesses, [], season_id=7)

        # score_earned = 140; expected season = 50 + 140 = 190
        # DB has only 120 (bug)
        mock_season_score = MagicMock()
        mock_season_score.points = 120
        self.mock_data_manager.get_player_season_score.return_value = mock_season_score

        self.mock_data_manager.get_all_players.return_value = {
            "p1": self._make_player("p1", 240, 1)  # all-time matches
        }

        result = self.game_runner.verify_daily_play(1)
        self.assertEqual(len(result), 1)
        self.assertIn("season_score", result[0]["diffs"])
        self.assertEqual(result[0]["diffs"]["season_score"]["expected"], 190)
        self.assertEqual(result[0]["diffs"]["season_score"]["actual"], 120)

    def test_no_season_skips_season_check(self):
        """When season_id is None, no season_score diff is reported."""
        snapshot = {"p1": self._make_player("p1", 100, 0, name="Dan")}
        guesses = [
            {
                "player_id": "p1",
                "guess_text": "4",
                "is_correct": True,
                "guessed_at": "2024-01-15 10:00:00",
            }
        ]
        self._setup_common_mocks(snapshot, guesses, [], season_id=None)

        self.mock_data_manager.get_all_players.return_value = {
            "p1": self._make_player("p1", 240, 1)
        }

        result = self.game_runner.verify_daily_play(1)
        self.assertEqual(result, [])
        self.mock_data_manager.get_player_season_score.assert_not_called()

    def test_multiple_players_partial_diffs(self):
        """Only players with diffs are included in the result."""
        snapshot = {
            "p1": self._make_player("p1", 100, 0, name="Alice"),
            "p2": self._make_player("p2", 200, 3, name="Bob"),
        }
        guesses = [
            {
                "player_id": "p1",
                "guess_text": "4",
                "is_correct": True,
                "guessed_at": "2024-01-15 10:00:00",
            },
            {
                "player_id": "p2",
                "guess_text": "4",
                "is_correct": True,
                "guessed_at": "2024-01-15 10:05:00",
            },
        ]
        self._setup_common_mocks(snapshot, guesses, [])

        # p1: streak=0→1, score_earned=100+20+10+10=140, final=240, streak=1
        # p2: streak=3→4, score_earned=100+20+10+5+20=155, final=355, streak=4
        # p1 matches; p2 has wrong score in DB
        self.mock_data_manager.get_all_players.return_value = {
            "p1": self._make_player("p1", 240, 1),  # correct
            "p2": self._make_player("p2", 999, 4),  # score wrong
        }

        result = self.game_runner.verify_daily_play(1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["player_id"], "p2")

    def test_format_verify_report(self):
        """format_verify_report produces a readable string with all diffs."""
        diffs = [
            {
                "player_id": "111",
                "player_name": "Alice",
                "diffs": {
                    "score": {"expected": 250, "actual": 230},
                    "streak": {"expected": 5, "actual": 4},
                },
            }
        ]
        report = GameRunner.format_verify_report(99, diffs)
        self.assertIn("⚠️", report)
        self.assertIn("99", report)
        self.assertIn("Alice", report)
        self.assertIn("score", report)
        self.assertIn("250", report)
        self.assertIn("230", report)
        self.assertIn("streak", report)

    def test_format_verify_report_negative_diff(self):
        """format_verify_report handles negative diffs correctly."""
        diffs = [
            {
                "player_id": "222",
                "player_name": "Bob",
                "diffs": {
                    "score": {"expected": 100, "actual": 150},
                },
            }
        ]
        report = GameRunner.format_verify_report(10, diffs)
        self.assertIn("-50", report)


if __name__ == "__main__":
    unittest.main()
