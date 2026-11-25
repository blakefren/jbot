import unittest
from unittest.mock import MagicMock, patch
from src.core.game_runner import GameRunner
from src.core.data_manager import DataManager
from src.core.player_manager import PlayerManager
from db.database import Database
from data.readers.question import Question
from tests.src.core._powerup_helpers import make_config


class TestVerifyDailyPlay(unittest.TestCase):
    """Tests for GameRunner.verify_daily_play and format_verify_report."""

    def setUp(self):
        self.db = Database(":memory:")
        self.addCleanup(self.db.close)
        self.data_manager = DataManager(self.db)
        self.player_manager = PlayerManager(self.data_manager)

        self.question = Question(
            question="What is 2+2?", answer="4", category="Math", clue_value=100
        )

        # ConfigReader reads .env, so a config double stands in for it.
        self.config = make_config(steal_cost=2, retro_steal_cost=4)
        self.config.is_seasons_enabled.return_value = False
        # The question selector wraps datasets/Gemini and is unused by verification.
        with patch("src.core.game_runner.ConfigReader", return_value=self.config):
            self.game_runner = GameRunner(
                MagicMock(), self.data_manager, player_manager=self.player_manager
            )

        self.season_id = None
        self.daily_question_id = None

    def _add_player(self, pid, score, streak, season_points=None, name=None, rest=0.0):
        """Seed a player as of the start of the day (captured by the snapshot)."""
        self.data_manager.create_player(pid, name or pid)
        self.data_manager.update_lifetime_stats(
            pid, score=score, answer_streak=streak, pending_rest_multiplier=rest
        )
        if season_points is not None:
            if self.season_id is None:
                self.season_id = self.data_manager.create_season(
                    "Test Season", "2024-01-01", "2024-01-31"
                )
            self.data_manager.update_season_score(
                pid, self.season_id, points=season_points
            )

    def _start_day(self):
        """Log today's question; this snapshots every player added so far."""
        self.daily_question_id = self.data_manager.log_daily_question(self.question)
        return self.daily_question_id

    def _guess(self, pid, text="4", guessed_at="2024-01-15 10:00:00"):
        self.data_manager.log_player_guess(
            pid, pid, self.daily_question_id, text, text == "4"
        )
        self.db.execute_update(
            "UPDATE guesses SET guessed_at = ? WHERE id = (SELECT MAX(id) FROM guesses)",
            (guessed_at,),
        )

    def _powerup(self, user_id, powerup_type, target_id, used_at):
        self.data_manager.log_powerup_usage(
            user_id, powerup_type, target_id, self.daily_question_id
        )
        self.db.execute_update(
            "UPDATE powerup_usage SET used_at = ? WHERE id = (SELECT MAX(id) FROM powerup_usage)",
            (used_at,),
        )

    def _set_db_state(self, pid, score, streak, season_points=None):
        """Set the persisted end-of-day state that verification compares against."""
        self.data_manager.update_lifetime_stats(pid, score=score, answer_streak=streak)
        if season_points is not None:
            self.data_manager.update_season_score(
                pid, self.season_id, points=season_points
            )

    def test_no_snapshot_returns_none(self):
        """When no snapshot exists, verification is reported as skipped."""
        question_id = self.data_manager.log_daily_question(self.question)  # no players
        result = self.game_runner.verify_daily_play(question_id)
        self.assertIsNone(result)

    def test_no_question_returns_none(self):
        """When the question cannot be found, verification is skipped."""
        self._add_player("p1", 100, 2)
        self.data_manager.create_daily_snapshot(999)  # snapshot with no question row
        result = self.game_runner.verify_daily_play(999)
        self.assertIsNone(result)

    def test_scores_match_no_diffs(self):
        """When DB state matches simulator prediction, returns empty list."""
        # P1 had score=100 and streak=2 before today.
        # Today they answer correctly on first try → score_earned = 100+20+10+10 + streak bonus
        # streak_length = 3, streak_bonus = 3*5 = 15
        # total = 155; final_score = 255; final_streak = 3
        self._add_player("p1", 100, 2, name="Alice")
        question_id = self._start_day()
        # Only accepted through the stored alternative answer, so a match proves
        # verification replays with the question's alternative answers.
        _, question_db_id = self.data_manager.get_daily_question_by_id(question_id)
        self.data_manager.add_alternative_answer(question_db_id, "quatre", "admin")
        self._guess("p1", "quatre")
        self._set_db_state("p1", 255, 3)

        result = self.game_runner.verify_daily_play(question_id)
        self.assertEqual(result, [])

    def test_score_mismatch_detected(self):
        """When the DB score doesn't match expected, a diff is returned."""
        self._add_player("p1", 100, 0, name="Alice")
        question_id = self._start_day()
        self._guess("p1")

        # score_earned = 100 + 20 + 10 + 10 = 140 (base+first_try+before_hint+fastest)
        # But DB only has 100 + 50 = 150 (wrong)
        self._set_db_state("p1", 150, 1)  # expected 240

        result = self.game_runner.verify_daily_play(question_id)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["player_id"], "p1")
        self.assertIn("score", result[0]["diffs"])
        self.assertEqual(result[0]["diffs"]["score"]["actual"], 150)

    def test_streak_mismatch_detected(self):
        """When the DB streak doesn't match expected, a diff is returned."""
        # P1 had streak=5; didn't answer today → streak should reset to 0.
        self._add_player("p1", 500, 5, name="Bob")
        question_id = self._start_day()
        # No guesses → end_of_day resets streak

        # DB streak wasn't reset (bug scenario): should be 0
        self._set_db_state("p1", 500, 5)

        result = self.game_runner.verify_daily_play(question_id)
        self.assertEqual(len(result), 1)
        self.assertIn("streak", result[0]["diffs"])
        self.assertEqual(result[0]["diffs"]["streak"]["expected"], 0)
        self.assertEqual(result[0]["diffs"]["streak"]["actual"], 5)

    def test_season_score_mismatch_detected(self):
        """When the season score doesn't match, a diff is returned."""
        self._add_player("p1", 100, 0, season_points=50, name="Carol")
        question_id = self._start_day()
        self._guess("p1")

        # score_earned = 140; expected season = 50 + 140 = 190
        # DB has only 120 (bug); all-time matches
        self._set_db_state("p1", 240, 1, season_points=120)

        result = self.game_runner.verify_daily_play(question_id)
        self.assertEqual(len(result), 1)
        self.assertIn("season_score", result[0]["diffs"])
        self.assertEqual(result[0]["diffs"]["season_score"]["expected"], 190)
        self.assertEqual(result[0]["diffs"]["season_score"]["actual"], 120)

    def test_no_season_skips_season_check(self):
        """When season_id is None, no season_score diff is reported."""
        self._add_player("p1", 100, 0, name="Dan")
        question_id = self._start_day()
        self._guess("p1")
        self._set_db_state("p1", 240, 1)

        # A season that began after the snapshot must not be compared against.
        self.season_id = self.data_manager.create_season(
            "Late Season", "2024-01-01", "2024-01-31"
        )
        self.data_manager.update_season_score("p1", self.season_id, points=1)

        result = self.game_runner.verify_daily_play(question_id)
        self.assertEqual(result, [])

    def test_multiple_players_partial_diffs(self):
        """Only players with diffs are included in the result."""
        self._add_player("p1", 100, 0, name="Alice")
        self._add_player("p2", 200, 3, name="Bob")
        question_id = self._start_day()
        self._guess("p1", guessed_at="2024-01-15 10:00:00")
        self._guess("p2", guessed_at="2024-01-15 10:05:00")

        # p1: streak=0→1, score_earned=100+20+10+10=140, final=240, streak=1
        # p2: streak=3→4, score_earned=100+20+10+5+20=155, final=355, streak=4
        # p1 matches; p2 has wrong score in DB
        self._set_db_state("p1", 240, 1)  # correct
        self._set_db_state("p2", 999, 4)  # score wrong

        result = self.game_runner.verify_daily_play(question_id)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["player_id"], "p2")
        self.assertEqual(result[0]["player_name"], "Bob")

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

    def test_rest_bonus_with_retroactive_jinx(self):
        """
        CRITICAL TEST: Verifies rest bonus + jinx scenario through verify_daily_play.

        This is the exact scenario that caused Q408/Q403 score verification alerts:
        - Player A answers correctly with rest multiplier (previous day's rest)
        - Player B jinxes Player A retroactively (after A already answered)
        - Verify that simulator correctly includes rest bonus in jinx transfer

        Scenario:
        - Player A: score=100, streak=0, pending_rest_multiplier=0.2 (20%)
        - Player A guesses correctly → scores 100+20+10+10 = 140 base
        - Rest multiplier applied: 140 * 0.2 = 28 rest bonus
        - Player A's total earned: 168
        - Player A's final score: 268
        - Player B jinxes retroactively → transfers 25% of 168 = 42 points
        - Player A final: 268 - 42 = 226
        - Player B final: 0 + 42 = 42
        """
        player_a_id = "player_a"
        player_b_id = "player_b"

        # Initial state: A has rest multiplier, B doesn't
        self._add_player(player_a_id, 100, 0, season_points=50, name="Alice", rest=0.2)
        self._add_player(player_b_id, 0, 0, season_points=0, name="Bob")
        question_id = self._start_day()

        # Events: A guesses correctly, B jinxes retroactively (after A answered)
        self._guess(player_a_id)
        self._powerup(player_b_id, "jinx_late", player_a_id, "2024-01-15 10:05:00")

        # DB state: Matches expected from simulator
        # A: 100 initial + 168 earned - 42 jinx = 226 final
        # B: 0 initial + 42 from jinx = 42 final
        # Season: A: 50 + 168 - 42 = 176; B: 0 + 42 = 42
        self._set_db_state(player_a_id, 226, 1, season_points=176)
        self._set_db_state(player_b_id, 42, 0, season_points=42)

        result = self.game_runner.verify_daily_play(question_id)

        # If rest bonus is correctly included in jinx, no diffs should be found
        self.assertEqual(
            result,
            [],
            "verify_daily_play should find no diffs when rest bonus is correctly "
            "included in jinx transfers. If this fails, jinx logic is wrong.",
        )


if __name__ == "__main__":
    unittest.main()
