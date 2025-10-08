import unittest
from unittest.mock import patch

from src.core.logger import Logger
from data.readers.question import Question
from database.database import Database


class TestLogger(unittest.TestCase):

    def setUp(self):
        """Set up for test cases."""
        self.db_path = ":memory:"
        self.db = Database(self.db_path)

        # Suppress print statements from logger
        patcher = patch("builtins.print")
        self.addCleanup(patcher.stop)
        self.mock_print = patcher.start()

        self.logger = Logger(self.db)

    def tearDown(self):
        """Clean up after tests."""
        self.logger.close()

    def test_log_daily_question(self):
        question = Question(
            category="TESTING",
            clue_value=100,
            question="Is this a test?",
            answer="Yes",
            data_source="test",
            metadata={},
        )
        users = ["user1", "user2"]
        self.logger.log_daily_question(question, users)

        # Verify question was inserted
        question_from_db = self.db.execute_query(
            "SELECT * FROM questions WHERE question_text = 'Is this a test?'"
        )
        self.assertEqual(len(question_from_db), 1)
        self.assertEqual(question_from_db[0]["category"], "TESTING")

        # Verify daily_question was logged
        daily_question_from_db = self.db.execute_query("SELECT * FROM daily_questions")
        self.assertEqual(len(daily_question_from_db), 1)

    def test_log_player_guess(self):
        # First, log a daily question to guess against
        q = Question(question="q1", answer="a1", category="cat", clue_value=100)
        self.logger.log_daily_question(q, [])
        daily_q = self.db.execute_query("SELECT id FROM daily_questions LIMIT 1")[0]

        self.logger.log_player_guess(
            "player1", "PlayerOne", daily_q["id"], "My Answer", True
        )

        guess_from_db = self.db.execute_query(
            "SELECT * FROM guesses WHERE player_id = 'player1'"
        )
        self.assertEqual(len(guess_from_db), 1)
        self.assertEqual(guess_from_db[0]["guess_text"], "My Answer")
        self.assertEqual(guess_from_db[0]["is_correct"], 1)

    def test_log_messaging_event(self):
        self.logger.log_messaging_event("to", "SMS", "12345", "Hello", "success")

        message_from_db = self.db.execute_query(
            "SELECT * FROM messages WHERE recipient_sender = '12345'"
        )
        self.assertEqual(len(message_from_db), 1)
        self.assertEqual(message_from_db[0]["content"], "Hello")
        self.assertEqual(message_from_db[0]["status"], "success")

    def test_read_guess_history(self):
        # Log questions and guesses
        q1 = Question(question="q1", answer="a1", category="cat", clue_value=100)
        q2 = Question(question="q2", answer="a2", category="cat", clue_value=100)
        self.logger.log_daily_question(q1, [])
        daily_q1_id = self.db.execute_query(
            "SELECT id FROM daily_questions ORDER BY id DESC LIMIT 1"
        )[0]["id"]
        self.logger.log_daily_question(q2, [])
        daily_q2_id = self.db.execute_query(
            "SELECT id FROM daily_questions ORDER BY id DESC LIMIT 1"
        )[0]["id"]

        self.logger.log_player_guess("123", "PlayerOne", daily_q1_id, "A1", True)
        self.logger.log_player_guess("456", "PlayerTwo", daily_q1_id, "A2", False)
        self.logger.log_player_guess("123", "PlayerOne", daily_q2_id, "A3", True)

        history = self.logger.read_guess_history()
        self.assertEqual(len(history), 3)

        user_history = self.logger.read_guess_history(user_id="123")
        self.assertEqual(len(user_history), 2)

        user_history = self.logger.read_guess_history(user_id="456")
        self.assertEqual(len(user_history), 1)

        user_history = self.logger.read_guess_history(
            user_id="999"
        )  # Non-existent user
        self.assertEqual(len(user_history), 0)


if __name__ == "__main__":
    unittest.main()
