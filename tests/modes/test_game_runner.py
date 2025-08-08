import unittest
import os
import csv
from unittest.mock import patch, MagicMock, mock_open

from modes.game_runner import GameRunner, GameType
from bot.subscriber import Subscriber
from readers.question import Question


class TestGameRunner(unittest.TestCase):
    def setUp(self):
        """Set up for the tests."""
        self.mock_question_selector = MagicMock()
        self.mock_question = Question(
            "Test Question", "Test Answer", "Test Category", 100
        )
        self.mock_question_selector.get_question_for_today.return_value = (
            self.mock_question
        )

        # Create a dummy subscribers file path
        self.test_subscribers_file = "test_subscribers.csv"

    def tearDown(self):
        """Tear down after tests."""
        if os.path.exists(self.test_subscribers_file):
            os.remove(self.test_subscribers_file)

    @patch("modes.game_runner.SUBSCRIBERS_FILE", "test_subscribers.csv")
    def test_initialization(self):
        """Test GameRunner initialization."""
        game_runner = GameRunner(self.mock_question_selector)
        self.assertEqual(game_runner.mode, GameType.SIMPLE)
        self.assertEqual(game_runner.question_selector, self.mock_question_selector)
        self.assertEqual(game_runner.subscribed_contexts, set())

    @patch("modes.game_runner.SUBSCRIBERS_FILE", "test_subscribers.csv")
    def test_load_subscribers(self):
        """Test loading subscribers from a CSV file."""
        # Create a dummy subscribers csv
        with open(self.test_subscribers_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "display_name", "is_channel"])
            writer.writerow(["123", "Test User", "False"])

        game_runner = GameRunner(self.mock_question_selector)
        self.assertEqual(len(game_runner.subscribed_contexts), 1)
        subscriber = list(game_runner.subscribed_contexts)[0]
        self.assertEqual(subscriber.id, 123)
        self.assertEqual(subscriber.display_name, "Test User")
        self.assertFalse(subscriber.is_channel)

    @patch("modes.game_runner.SUBSCRIBERS_FILE", "test_subscribers.csv")
    def test_add_and_remove_subscriber(self):
        """Test adding and removing a subscriber."""
        game_runner = GameRunner(self.mock_question_selector)
        subscriber = Subscriber("456", "Another User", True)

        game_runner.add_subscriber(subscriber)
        self.assertIn(subscriber, game_runner.subscribed_contexts)

        # Verify it was saved
        with open(self.test_subscribers_file, "r") as f:
            content = f.read()
            self.assertIn("456,Another User,True", content)

        game_runner.remove_subscriber(subscriber)
        self.assertNotIn(subscriber, game_runner.subscribed_contexts)

        # Verify it was removed from file
        with open(self.test_subscribers_file, "r") as f:
            content = f.read()
            self.assertNotIn("456,Another User,True", content)

    @patch("modes.game_runner.SUBSCRIBERS_FILE", "test_subscribers.csv")
    def test_change_mode(self):
        """Test changing the game mode."""
        game_runner = GameRunner(self.mock_question_selector)
        self.assertEqual(game_runner.mode, GameType.SIMPLE)
        game_runner.change_mode(GameType.POKER)
        self.assertEqual(game_runner.mode, GameType.POKER)

    @patch("builtins.print")
    @patch("modes.game_runner.SUBSCRIBERS_FILE", "test_subscribers.csv")
    def test_send_morning_message(self, mock_print):
        """Test sending the morning message."""
        game_runner = GameRunner(self.mock_question_selector)
        subscriber = Subscriber("789", "Morning Person", False)
        game_runner.add_subscriber(subscriber)

        game_runner.send_morning_message()

        self.mock_question_selector.get_question_for_today.assert_called_once()
        mock_print.assert_called_with(
            f"Sending morning message to {subscriber.display_name}: {self.mock_question.question}"
        )

    @patch("builtins.print")
    @patch("modes.game_runner.SUBSCRIBERS_FILE", "test_subscribers.csv")
    def test_send_evening_message(self, mock_print):
        """Test sending the evening message."""
        game_runner = GameRunner(self.mock_question_selector)
        subscriber = Subscriber("101", "Evening Person", False)
        game_runner.add_subscriber(subscriber)

        game_runner.send_evening_message()

        self.mock_question_selector.get_question_for_today.assert_called_once()
        mock_print.assert_called_with(
            f"Sending evening message to {subscriber.display_name}: {self.mock_question.answer}"
        )

    @patch("modes.game_runner.SUBSCRIBERS_FILE", "test_subscribers.csv")
    def test_handle_guess(self):
        """Test handling a guess."""
        game_runner = GameRunner(self.mock_question_selector)
        subscriber = Subscriber("112", "Guesser", False)

        # Correct guess
        with patch.object(game_runner, "calculate_scores", MagicMock()) as mock_calc:
            game_runner.handle_guess(subscriber, "Test Answer")
            # TODO: Add assertions for score changes when implemented

        # Incorrect guess
        with patch.object(game_runner, "calculate_scores", MagicMock()) as mock_calc:
            game_runner.handle_guess(subscriber, "Wrong Answer")
            # TODO: Add assertions for score changes when implemented


if __name__ == "__main__":
    unittest.main()
