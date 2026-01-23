import unittest
from unittest.mock import MagicMock, patch
from datetime import date, timedelta
from src.core.game_runner import GameRunner
from data.readers.question import Question


class TestRecalculateScores(unittest.TestCase):
    def setUp(self):
        self.mock_question_selector = MagicMock()
        self.mock_data_manager = MagicMock()
        self.game_runner = GameRunner(
            self.mock_question_selector, self.mock_data_manager
        )

        # Setup daily question
        self.game_runner.daily_q = Question(
            question="Q", answer="800-899", category="C", clue_value=100
        )
        self.game_runner.daily_question_id = 1

        # Mock config
        self.game_runner.config = MagicMock()
        self.defaults = {
            "JBOT_BONUS_TRY_CSV": "20,10,5",
            "JBOT_BONUS_FASTEST_CSV": "10,5,5",
            "JBOT_BONUS_BEFORE_HINT": "10",
            "JBOT_BONUS_STREAK_PER_DAY": "5",
            "JBOT_BONUS_STREAK_CAP": "25",
            "JBOT_EMOJI_FIRST_TRY": "🎯",
            "JBOT_EMOJI_BEFORE_HINT": "🧠",
            "JBOT_EMOJI_FASTEST": "🥇",
            "JBOT_EMOJI_FASTEST_CSV": "🥇,🥈,🥉",
            "JBOT_EMOJI_STREAK": "🔥",
            "JBOT_RIDDLE_HISTORY_DAYS": "30",
            "JBOT_QUESTION_RETRIES": "10",
        }
        self.game_runner.config.get.side_effect = lambda k, d=None: self.defaults.get(k)

        # Mock PlayerManager
        self.game_runner.player_manager = MagicMock()

        # Mock get_player to return a mock object with answer_streak
        mock_player = MagicMock()
        mock_player.answer_streak = 0
        mock_player.score = 0
        self.game_runner.player_manager.get_player.return_value = mock_player
        self.game_runner.player_manager.get_all_players.return_value = {}

        # Default snapshot to None (so tests fall back to player_manager)
        self.mock_data_manager.get_daily_snapshot.return_value = None

        # Mock mark_matching_guesses_as_correct to return 0 by default
        self.mock_data_manager.mark_matching_guesses_as_correct.return_value = 0

    def test_recalculate_scores_success(self):
        # Setup guesses
        # Player 1: "800" (Wrong initially)
        # Player 2: "900" (Wrong)
        guesses = [
            {
                "id": 1,
                "daily_question_id": 1,
                "player_id": "p1",
                "guess_text": "800",
                "is_correct": 0,
                "guessed_at": "2023-01-01 10:00:00",
            },
            {
                "id": 2,
                "daily_question_id": 1,
                "player_id": "p2",
                "guess_text": "900",
                "is_correct": 0,
                "guessed_at": "2023-01-01 10:05:00",
            },
        ]
        self.mock_data_manager.get_guesses_for_daily_question.return_value = guesses
        self.mock_data_manager.get_hint_sent_timestamp.return_value = None
        self.mock_data_manager.get_alternative_answers.return_value = []
        self.mock_data_manager.get_powerup_usage_for_daily_question.return_value = []

        # Run recalculation with "800"
        result = self.game_runner.recalculate_scores_for_new_answer("800", "admin1")

        # Verify
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["updated_players"], 1)
        # 100 base + 20 first try + 10 before hint + 10 fastest = 140
        self.assertEqual(result["total_refunded"], 140)

        # Check DB calls
        self.mock_data_manager.add_alternative_answer.assert_called_with(
            1, "800", "admin1"
        )
        self.game_runner.player_manager.update_score.assert_called_with("p1", 140)
        self.game_runner.player_manager.set_streak.assert_called_with("p1", 1)

    def test_recalculate_scores_already_correct(self):
        # Player 1: "800-899" (Correct)
        guesses = [
            {
                "id": 1,
                "daily_question_id": 1,
                "player_id": "p1",
                "guess_text": "800-899",
                "is_correct": 1,
                "guessed_at": "2023-01-01 10:00:00",
            }
        ]
        self.mock_data_manager.get_guesses_for_daily_question.return_value = guesses

        result = self.game_runner.recalculate_scores_for_new_answer("800", "admin1")

        self.assertEqual(result["updated_players"], 0)
        self.game_runner.player_manager.update_score.assert_not_called()

    def test_recalculate_scores_uses_snapshot(self):
        # Setup guesses
        guesses = [
            {
                "id": 1,
                "daily_question_id": 1,
                "player_id": "p1",
                "guess_text": "800",
                "is_correct": 0,
                "guessed_at": "2023-01-01 10:00:00",
            }
        ]
        self.mock_data_manager.get_guesses_for_daily_question.return_value = guesses
        self.mock_data_manager.get_hint_sent_timestamp.return_value = None
        self.mock_data_manager.get_alternative_answers.return_value = []
        self.mock_data_manager.get_powerup_usages_for_question.return_value = []

        # Mock snapshot
        mock_snapshot = {"p1": MagicMock(score=1000, answer_streak=10)}
        self.mock_data_manager.get_daily_snapshot.return_value = mock_snapshot

        # Run recalculation
        self.game_runner.recalculate_scores_for_new_answer("800", "admin1")

        # Verify snapshot was requested
        self.mock_data_manager.get_daily_snapshot.assert_called_with(1)

        # Verify player manager was NOT called to get current players (since snapshot was used)
        self.game_runner.player_manager.get_all_players.assert_not_called()

    def test_recalculate_scores_dry_run(self):
        # Setup guesses
        guesses = [
            {
                "id": 1,
                "daily_question_id": 1,
                "player_id": "p1",
                "guess_text": "800",
                "is_correct": 0,
                "guessed_at": "2023-01-01 10:00:00",
            }
        ]
        self.mock_data_manager.get_guesses_for_daily_question.return_value = guesses
        self.mock_data_manager.get_hint_sent_timestamp.return_value = None
        self.mock_data_manager.get_alternative_answers.return_value = []
        self.mock_data_manager.get_powerup_usage_for_daily_question.return_value = []

        # Run recalculation with dry_run=True
        result = self.game_runner.recalculate_scores_for_new_answer(
            "800", "admin1", dry_run=True
        )

        # Verify results are calculated but not applied
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["updated_players"], 1)
        self.assertEqual(result["total_refunded"], 140)

        # Check DB calls are NOT made
        self.mock_data_manager.add_alternative_answer.assert_not_called()
        self.game_runner.player_manager.update_score.assert_not_called()
        self.game_runner.player_manager.set_streak.assert_not_called()
        self.mock_data_manager.log_score_adjustment.assert_not_called()

    def test_recalculate_scores_no_active_question_uses_most_recent(self):
        """Test that recalculate uses most recent question when no active question exists."""
        # Clear the active daily question (simulating after evening message)
        self.game_runner.daily_q = None
        self.game_runner.daily_question_id = None

        # Mock get_most_recent_daily_question to return a question from today
        recent_question = Question(
            question="Q", answer="800-899", category="C", clue_value=100
        )
        recent_question_id = 1
        recent_date = date.today()
        self.mock_data_manager.get_most_recent_daily_question.return_value = (
            recent_question,
            recent_question_id,
            recent_date,
        )

        # Setup guesses
        guesses = [
            {
                "id": 1,
                "daily_question_id": 1,
                "player_id": "p1",
                "guess_text": "800",
                "is_correct": 0,
                "guessed_at": "2023-01-01 10:00:00",
            }
        ]
        self.mock_data_manager.get_guesses_for_daily_question.return_value = guesses
        self.mock_data_manager.get_hint_sent_timestamp.return_value = None
        self.mock_data_manager.get_alternative_answers.return_value = []
        self.mock_data_manager.get_powerup_usage_for_daily_question.return_value = []

        # Run recalculation
        result = self.game_runner.recalculate_scores_for_new_answer("800", "admin1")

        # Verify success
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["updated_players"], 1)
        self.mock_data_manager.get_most_recent_daily_question.assert_called_once()

        # No age warning for same-day question
        self.assertEqual(result.get("age_warning"), "")

    def test_recalculate_scores_old_question_warning(self):
        """Test that recalculate warns when correcting an old question."""
        # Clear the active daily question
        self.game_runner.daily_q = None
        self.game_runner.daily_question_id = None

        # Mock get_most_recent_daily_question to return a question from 2 days ago
        recent_question = Question(
            question="Q", answer="800-899", category="C", clue_value=100
        )
        recent_question_id = 1
        recent_date = date.today() - timedelta(days=2)
        self.mock_data_manager.get_most_recent_daily_question.return_value = (
            recent_question,
            recent_question_id,
            recent_date,
        )

        # Setup minimal guesses
        guesses = []
        self.mock_data_manager.get_guesses_for_daily_question.return_value = guesses
        self.mock_data_manager.get_hint_sent_timestamp.return_value = None
        self.mock_data_manager.get_alternative_answers.return_value = []
        self.mock_data_manager.get_powerup_usage_for_daily_question.return_value = []

        # Run recalculation
        result = self.game_runner.recalculate_scores_for_new_answer("800", "admin1")

        # Verify age warning is present
        self.assertEqual(result["status"], "success")
        self.assertIn("2 day(s) old", result["age_warning"])

    def test_recalculate_scores_no_questions_exist(self):
        """Test that recalculate errors gracefully when no questions exist."""
        # Clear the active daily question
        self.game_runner.daily_q = None
        self.game_runner.daily_question_id = None

        # Mock get_most_recent_daily_question to return None
        self.mock_data_manager.get_most_recent_daily_question.return_value = None

        # Run recalculation
        result = self.game_runner.recalculate_scores_for_new_answer("800", "admin1")

        # Verify error
        self.assertEqual(result["status"], "error")
        self.assertIn("No daily question found", result["message"])
        self.mock_data_manager.add_alternative_answer.assert_not_called()

    def test_recalculate_marks_guesses_as_correct(self):
        """Test that recalculate marks previously incorrect guesses as correct in DB."""
        # Setup guesses: p1 guessed "800" (initially wrong), p2 guessed "900" (wrong)
        guesses = [
            {
                "id": 1,
                "daily_question_id": 1,
                "player_id": "p1",
                "guess_text": "800",
                "is_correct": 0,
                "guessed_at": "2023-01-01 10:00:00",
            },
            {
                "id": 2,
                "daily_question_id": 1,
                "player_id": "p2",
                "guess_text": "900",
                "is_correct": 0,
                "guessed_at": "2023-01-01 10:05:00",
            },
        ]
        self.mock_data_manager.get_guesses_for_daily_question.return_value = guesses
        self.mock_data_manager.get_hint_sent_timestamp.return_value = None
        self.mock_data_manager.get_alternative_answers.return_value = []
        self.mock_data_manager.get_powerup_usage_for_daily_question.return_value = []

        # Mock mark_matching_guesses_as_correct to return 1 (one guess was marked)
        self.mock_data_manager.mark_matching_guesses_as_correct.return_value = 1

        # Run recalculation with "800" (dry_run=False)
        result = self.game_runner.recalculate_scores_for_new_answer(
            "800", "admin1", dry_run=False
        )

        # Verify the alternative answer was added
        self.mock_data_manager.add_alternative_answer.assert_called_with(
            1, "800", "admin1"
        )

        # Verify mark_matching_guesses_as_correct was called with correct parameters
        self.mock_data_manager.mark_matching_guesses_as_correct.assert_called_once()
        call_args = self.mock_data_manager.mark_matching_guesses_as_correct.call_args
        self.assertEqual(call_args[0][0], 1)  # daily_question_id
        self.assertEqual(call_args[0][1], "800")  # new_answer
        # Third argument is the match function, just verify it's callable
        self.assertTrue(callable(call_args[0][2]))
