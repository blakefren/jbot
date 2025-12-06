import unittest
from unittest.mock import MagicMock, call
from src.core.game_runner import GameRunner
from src.core.player import Player


class TestGameRunnerStreaks(unittest.TestCase):
    def setUp(self):
        self.mock_question_selector = MagicMock()
        self.mock_data_manager = MagicMock()
        self.mock_player_manager = MagicMock()

        self.game_runner = GameRunner(
            self.mock_question_selector, self.mock_data_manager
        )
        self.game_runner.player_manager = self.mock_player_manager

        self.game_runner.daily_question_id = 1

        self.player1 = Player(id="1", name="Alice", answer_streak=3)
        self.player2 = Player(id="2", name="Bob", answer_streak=5)
        self.player3 = Player(id="3", name="Charlie", answer_streak=0)

        self.mock_player_manager.get_all_players.return_value = {
            "1": self.player1,
            "2": self.player2,
            "3": self.player3,
        }

    def test_update_streaks_resets_for_incorrect_or_no_answer(self):
        """
        Test that streaks are reset for players who did not answer correctly,
        and maintained for those who did.
        """
        # Player 1 answered correctly, Player 3 answered correctly, Player 2 did not.
        self.mock_data_manager.read_guess_history.return_value = [
            {"daily_question_id": 1, "player_id": "1", "is_correct": True},
            {"daily_question_id": 1, "player_id": "3", "is_correct": True},
        ]

        self.game_runner.update_streaks()
        # Verify that only Player 2's streak was reset via PlayerManager
        self.mock_player_manager.reset_streak.assert_called_once_with("2")

    def test_update_streaks_all_correct(self):
        """Test that no streaks are reset if all players answered correctly."""
        self.mock_data_manager.read_guess_history.return_value = [
            {"daily_question_id": 1, "player_id": "1", "is_correct": True},
            {"daily_question_id": 1, "player_id": "2", "is_correct": True},
            {"daily_question_id": 1, "player_id": "3", "is_correct": True},
        ]

        self.game_runner.update_streaks()

        # No resets should be triggered when all answered correctly
        self.mock_player_manager.reset_streak.assert_not_called()

    def test_update_streaks_no_correct_answers(self):
        """Test that all streaks are reset if no one answered correctly."""
        self.mock_data_manager.read_guess_history.return_value = [
            {"daily_question_id": 1, "player_id": "1", "is_correct": False},
        ]

        self.game_runner.update_streaks()

        # Players with non-zero streaks should be reset (1 and 2), 3 stays at 0
        calls = [
            call.args[0]
            for call in self.mock_player_manager.reset_streak.call_args_list
        ]
        self.assertCountEqual(calls, ["1", "2"])

    def test_update_streaks_no_daily_question(self):
        """Test that the function exits early if there is no daily question ID."""
        self.game_runner.daily_question_id = None
        self.game_runner.update_streaks()
        self.mock_data_manager.read_guess_history.assert_not_called()


if __name__ == "__main__":
    unittest.main()
