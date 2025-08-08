import unittest
import os
import sys
from unittest.mock import patch, MagicMock

# Add project root to path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from log.logger import Logger
from readers.question import Question


class TestLogger(unittest.TestCase):

    def setUp(self):
        """Set up for test cases."""
        self.log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "log")
        self.history_log_path = os.path.join(self.log_dir, "history.log")
        self.messaging_log_path = os.path.join(self.log_dir, "messaging.log")
        self.guesses_log_path = os.path.join(self.log_dir, "guesses.log")

        # Suppress print statements from logger
        patcher = patch("builtins.print")
        self.addCleanup(patcher.stop)
        self.mock_print = patcher.start()

        self.logger = Logger()

        # Clear log files before each test
        for log_file in [
            self.history_log_path,
            self.messaging_log_path,
            self.guesses_log_path,
        ]:
            if os.path.exists(log_file):
                with open(log_file, "w") as f:
                    f.truncate(0)

    def tearDown(self):
        """Clean up after tests."""
        for log_file in [
            self.history_log_path,
            self.messaging_log_path,
            self.guesses_log_path,
        ]:
            if os.path.exists(log_file):
                os.remove(log_file)

    def test_log_daily_question(self):
        question = Question(
            id="test_id_123",
            category="TESTING",
            clue_value=100,
            question="Is this a test?",
            answer="Yes",
            data_source="test",
            metadata={},
        )
        users = ["user1", "user2"]
        self.logger.log_daily_question(question, users)

        with open(self.history_log_path, "r") as f:
            content = f.read()
            self.assertIn("Daily Question Sent", content)
            self.assertIn("ID: test_id_123", content)
            self.assertIn("Category: TESTING", content)
            self.assertIn("Value: $100", content)
            self.assertIn("Question: 'Is this a test?'", content)
            self.assertIn("Answer: 'Yes'", content)
            self.assertIn("Sent To: user1, user2", content)

    def test_log_player_guess(self):
        self.logger.log_player_guess("player1", "PlayerOne", "q1", "My Answer", True)
        with open(self.guesses_log_path, "r") as f:
            content = f.read()
            self.assertIn(
                "PlayerGuess - PlayerID: player1, PlayerName: 'PlayerOne', QuestionID: q1, Guess: 'My Answer', Correct: True",
                content,
            )

    def test_log_messaging_event(self):
        self.logger.log_messaging_event("to", "SMS", "12345", "Hello", "success")
        with open(self.messaging_log_path, "r") as f:
            content = f.read()
            self.assertIn(
                "Message Event - Direction: to, Method: SMS, Recipient: 12345, Content: 'Hello', Status: success",
                content,
            )

    def test_read_guess_history(self):
        self.logger.log_player_guess("player1", "PlayerOne", "1", "A1", True)
        self.logger.log_player_guess("player2", "PlayerTwo", "1", "A2", False)
        self.logger.log_player_guess("player1", "PlayerOne", "2", "A3", True)

        history = self.logger.read_guess_history()
        self.assertEqual(len(history), 3)

        user_history = self.logger.read_guess_history(user_id=123)  # Non-existent user
        self.assertEqual(len(user_history), 0)

    def test_deduplicate_guesses(self):
        guesses = [
            {
                "timestamp": "2023-01-01 12:00:00",
                "PlayerID": "1",
                "QuestionID": "100",
                "Guess": "A",
            },
            {
                "timestamp": "2023-01-01 12:05:00",
                "PlayerID": "1",
                "QuestionID": "100",
                "Guess": "B",
            },  # newer
            {
                "timestamp": "2023-01-01 12:01:00",
                "PlayerID": "2",
                "QuestionID": "100",
                "Guess": "C",
            },
            {
                "timestamp": "2023-01-01 12:02:00",
                "PlayerID": "1",
                "QuestionID": "101",
                "Guess": "D",
            },
        ]

        deduplicated = self.logger._deduplicate_guesses(guesses)

        # Create a set of tuples to check for presence, ignoring timestamp which is not preserved in the current implementation
        deduplicated_set = {
            (g["PlayerID"], g["QuestionID"], g["Guess"]) for g in deduplicated
        }

        self.assertIn(("1", "100", "B"), deduplicated_set)
        self.assertIn(("2", "100", "C"), deduplicated_set)
        self.assertIn(("1", "101", "D"), deduplicated_set)
        self.assertEqual(len(deduplicated), 3)

    def test_get_guess_metrics(self):
        history = [
            {"PlayerID": "1", "PlayerName": "Alice", "QuestionID": 10, "Correct": True},
            {
                "PlayerID": "1",
                "PlayerName": "Alice",
                "QuestionID": 11,
                "Correct": False,
            },
            {"PlayerID": "2", "PlayerName": "Bob", "QuestionID": 10, "Correct": True},
        ]
        questions = [MagicMock(id=10, clue_value=200), MagicMock(id=11, clue_value=400)]

        metrics = self.logger.get_guess_metrics(history, questions)

        self.assertEqual(metrics["total_guesses"], 3)
        self.assertEqual(metrics["unique_questions"], 2)
        self.assertAlmostEqual(metrics["global_correct_rate"], 2 / 3)
        self.assertEqual(metrics["global_score"], 400)  # 200 (Alice) + 200 (Bob)

        self.assertEqual(metrics["players"]["1"]["total_guesses"], 2)
        self.assertEqual(metrics["players"]["1"]["correct_guesses"], 1)
        self.assertEqual(metrics["players"]["1"]["score"], 200)
        self.assertEqual(metrics["players"]["1"]["correct_rate"], 0.5)

        self.assertEqual(metrics["players"]["2"]["total_guesses"], 1)
        self.assertEqual(metrics["players"]["2"]["correct_guesses"], 1)
        self.assertEqual(metrics["players"]["2"]["score"], 200)
        self.assertEqual(metrics["players"]["2"]["correct_rate"], 1.0)


if __name__ == "__main__":
    unittest.main(argv=["first-arg-is-ignored"], exit=False)
