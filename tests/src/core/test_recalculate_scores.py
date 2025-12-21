import unittest
from unittest.mock import MagicMock, patch
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
        self.game_runner.config.get.side_effect = lambda k, d=None: d

        # Mock PlayerManager
        self.game_runner.player_manager = MagicMock()

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

        # Run recalculation with "800"
        result = self.game_runner.recalculate_scores_for_new_answer("800", "admin1")

        # Verify
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["updated_players"], 1)
        # 100 base + 20 first try + 10 before hint (since no hint sent)
        self.assertEqual(result["total_refunded"], 130)

        # Check DB calls
        self.mock_data_manager.add_alternative_answer.assert_called_with(
            1, "800", "admin1"
        )
        self.mock_data_manager.mark_guess_as_correct.assert_called()  # Should update guess
        self.game_runner.player_manager.update_score.assert_called_with("p1", 130)
        self.game_runner.player_manager.increment_streak.assert_called_with("p1")

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
