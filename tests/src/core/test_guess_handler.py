import unittest
from unittest.mock import MagicMock, patch
from src.core.guess_handler import GuessHandler, AlreadyAnsweredCorrectlyError
from data.readers.question import Question


class TestGuessHandler(unittest.TestCase):
    def setUp(self):
        self.data_manager = MagicMock()
        self.daily_question = Question(
            "Test Question", "Test Answer", "Test Category", 100, "Test Hint"
        )
        self.daily_question_id = 123
        self.managers = {"test_manager": MagicMock()}

        self.guess_handler = GuessHandler(
            self.data_manager,
            self.daily_question,
            self.daily_question_id,
            self.managers,
        )

    def test_handle_guess_correct(self):
        """Test handling a correct guess."""
        player_id = 1
        player_name = "PlayerOne"
        guess = "Test Answer"

        self.data_manager.read_guess_history.return_value = []

        is_correct, num_guesses = self.guess_handler.handle_guess(
            player_id, player_name, guess
        )

        self.assertTrue(is_correct)
        self.assertEqual(num_guesses, 1)
        self.data_manager.log_player_guess.assert_called_once_with(
            player_id, player_name, self.daily_question_id, guess.lower(), True
        )
        self.managers["test_manager"].on_guess.assert_called_once_with(
            player_id, player_name, guess, True
        )

    def test_handle_guess_incorrect(self):
        """Test handling an incorrect guess."""
        player_id = 2
        player_name = "PlayerTwo"
        guess = "Wrong Answer"

        self.data_manager.read_guess_history.return_value = []

        is_correct, num_guesses = self.guess_handler.handle_guess(
            player_id, player_name, guess
        )

        self.assertFalse(is_correct)
        self.assertEqual(num_guesses, 1)
        self.data_manager.log_player_guess.assert_called_once_with(
            player_id, player_name, self.daily_question_id, guess.lower(), False
        )
        self.managers["test_manager"].on_guess.assert_called_once_with(
            player_id, player_name, guess, False
        )

    def test_handle_guess_already_answered_correctly(self):
        """Test that an error is raised if a player has already answered correctly."""
        player_id = 3
        player_name = "PlayerThree"
        guess = "Another Answer"

        self.data_manager.read_guess_history.return_value = [
            {"daily_question_id": self.daily_question_id, "is_correct": True}
        ]

        with self.assertRaises(AlreadyAnsweredCorrectlyError):
            self.guess_handler.handle_guess(player_id, player_name, guess)

    def test_get_player_guesses(self):
        """Test retrieving a player's guesses for the current question."""
        player_id = 4
        self.data_manager.read_guess_history.return_value = [
            {"daily_question_id": self.daily_question_id, "guess_text": "guess1"},
            {"daily_question_id": self.daily_question_id, "guess_text": "guess2"},
            {"daily_question_id": 999, "guess_text": "old_guess"},  # Not for today
        ]

        guesses = self.guess_handler.get_player_guesses(player_id)
        self.assertEqual(len(guesses), 2)
        self.assertIn("guess1", guesses)
        self.assertIn("guess2", guesses)

    def test_has_answered_correctly_today_true(self):
        """Test checking if a player has answered correctly today when they have."""
        player_id = 5
        self.data_manager.read_guess_history.return_value = [
            {"daily_question_id": self.daily_question_id, "is_correct": True}
        ]

        self.assertTrue(self.guess_handler.has_answered_correctly_today(player_id))

    def test_has_answered_correctly_today_false(self):
        """Test checking if a player has answered correctly today when they have not."""
        player_id = 6
        self.data_manager.read_guess_history.return_value = [
            {"daily_question_id": self.daily_question_id, "is_correct": False}
        ]

        self.assertFalse(self.guess_handler.has_answered_correctly_today(player_id))


if __name__ == "__main__":
    unittest.main()
