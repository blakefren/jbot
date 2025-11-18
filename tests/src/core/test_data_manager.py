import unittest
from unittest.mock import patch, MagicMock
from datetime import date

from src.core.data_manager import DataManager
from src.core.player import Player
from src.core.subscriber import Subscriber
from data.readers.question import Question
from db.database import Database


class TestDataManager(unittest.TestCase):
    def test_save_players(self):
        """Test DataManager.save_players writes correct player data to DB."""
        mock_db = patch.object(self.data_manager, "db", autospec=True).start()
        players = {
            "1": Player(
                id="1", name="Alice", score=42, answer_streak=3, active_shield=True
            ),
            "2": Player(
                id="2", name="Bob", score=0, answer_streak=0, active_shield=False
            ),
        }
        self.data_manager.save_players(players)
        # Should call execute_update twice, once for each player
        self.assertEqual(mock_db.execute_update.call_count, 2)
        # Check first call params
        first_call = mock_db.execute_update.call_args_list[0]
        query = first_call[0][0]
        params = first_call[0][1]
        self.assertIn("INSERT INTO players", query)
        self.assertEqual(params[0], "1")
        self.assertEqual(params[1], "Alice")
        self.assertEqual(params[2], 42)
        self.assertEqual(params[3], 3)
        self.assertEqual(params[4], True)
        # Check second call params
        second_call = mock_db.execute_update.call_args_list[1]
        params2 = second_call[0][1]
        self.assertEqual(params2[0], "2")
        self.assertEqual(params2[1], "Bob")
        self.assertEqual(params2[2], 0)
        self.assertEqual(params2[3], 0)
        self.assertEqual(params2[4], False)
        patch.stopall()

    def test_load_players(self):
        """Test DataManager.load_players returns correct player dict."""
        # Mock the database execute_query method
        self.db.execute_query = lambda query: [
            {
                "id": "1",
                "name": "Alice",
                "score": 42,
                "answer_streak": 3,
                "active_shield": 1,
            },
            {
                "id": "2",
                "name": "Bob",
                "score": 0,
                "answer_streak": 0,
                "active_shield": 0,
            },
        ]
        players = self.data_manager.load_players()
        self.assertEqual(players["1"].name, "Alice")
        self.assertEqual(players["1"].score, 42)
        self.assertEqual(players["1"].answer_streak, 3)
        self.assertTrue(players["1"].active_shield)
        self.assertFalse(players["2"].active_shield)

        # Test empty DB
        self.db.execute_query = lambda query: []
        players = self.data_manager.load_players()
        self.assertEqual(players, {})

    def setUp(self):
        """Set up for test cases."""
        self.db_path = ":memory:"
        self.db = Database(self.db_path)
        self.data_manager = DataManager(self.db)

    def tearDown(self):
        """Clean up after tests."""
        self.db.close()

    def test_log_daily_question(self):
        question = Question(
            category="TESTING",
            clue_value=100,
            question="Is this a test?",
            answer="Yes",
            data_source="test",
            metadata={},
        )
        self.data_manager.log_daily_question(question)

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
        daily_q_id = self.data_manager.log_daily_question(q)

        self.data_manager.log_player_guess(
            "player1", "PlayerOne", daily_q_id, "My Answer", True
        )

        guess_from_db = self.db.execute_query(
            "SELECT * FROM guesses WHERE player_id = 'player1'"
        )
        self.assertEqual(len(guess_from_db), 1)
        self.assertEqual(guess_from_db[0]["guess_text"], "My Answer")
        self.assertEqual(guess_from_db[0]["is_correct"], 1)

    def test_log_messaging_event(self):
        self.data_manager.log_messaging_event(
            "outgoing", "discord", "12345", "Hello", "success"
        )

        message_from_db = self.db.execute_query(
            "SELECT * FROM messages WHERE recipient_sender = '12345'"
        )
        self.assertEqual(len(message_from_db), 1)
        self.assertEqual(message_from_db[0]["content"], "Hello")
        self.assertEqual(message_from_db[0]["status"], "success")

    def test_get_player_ids_with_role(self):
        """Test retrieving player IDs for a given role."""
        role_name = "Winner"
        # Mock the DB response
        self.data_manager.db.execute_query = lambda query, params: [
            {"player_id": "123"},
            {"player_id": "456"},
        ]
        player_ids = self.data_manager.get_player_ids_with_role(role_name)
        self.assertEqual(player_ids, {"123", "456"})

        # Test with no results
        self.data_manager.db.execute_query = lambda query, params: []
        player_ids = self.data_manager.get_player_ids_with_role(role_name)
        self.assertEqual(player_ids, set())

    def test_read_guess_history(self):
        # Log questions and guesses
        q1 = Question(question="q1", answer="a1", category="cat", clue_value=100)
        q2 = Question(question="q2", answer="a2", category="cat", clue_value=100)
        daily_q1_id = self.data_manager.log_daily_question(q1)
        # This will not create a new daily question due to the date check
        self.data_manager.log_daily_question(q2)

        self.data_manager.log_player_guess("123", "PlayerOne", daily_q1_id, "A1", True)
        self.data_manager.log_player_guess("456", "PlayerTwo", daily_q1_id, "A2", False)
        self.data_manager.log_player_guess("123", "PlayerOne", daily_q1_id, "A3", True)

        history = self.data_manager.read_guess_history()
        self.assertEqual(len(history), 3)

        user_history = self.data_manager.read_guess_history(user_id="123")
        self.assertEqual(len(user_history), 2)

        user_history = self.data_manager.read_guess_history(user_id="456")
        self.assertEqual(len(user_history), 1)

        user_history = self.data_manager.read_guess_history(
            user_id="999"
        )  # Non-existent user
        self.assertEqual(len(user_history), 0)

    def test_log_score_adjustment(self):
        """Test logging a score adjustment for a player."""
        player_id = "player1"
        admin_id = "admin1"
        amount = 50
        reason = "Manual refund"
        self.data_manager.log_score_adjustment(player_id, admin_id, amount, reason)

        result = self.db.execute_query(
            "SELECT * FROM score_adjustments WHERE player_id = ? AND admin_id = ?",
            (player_id, admin_id),
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["amount"], amount)
        self.assertEqual(result[0]["reason"], reason)

    def test_assign_role_to_player(self):
        """Test assigning a role to a player."""
        player_id = "player1"
        role_name = "New Role"

        # Mock DB methods
        self.data_manager.db.execute_query = MagicMock(return_value=[])
        self.data_manager.db.execute_update = MagicMock(return_value=(None, 1))

        self.data_manager.assign_role_to_player(player_id, role_name)

        # Verify role was created and assigned
        self.assertEqual(self.data_manager.db.execute_update.call_count, 2)

    def test_clear_player_roles(self):
        """Test clearing all player roles."""
        # Mock DB method
        self.data_manager.db.execute_update = MagicMock(return_value=(None, 1))
        self.data_manager.clear_player_roles()
        self.assertEqual(self.data_manager.db.execute_update.call_count, 1)

    def test_get_all_subscribers(self):
        """Test getting all subscribers from the database."""
        self.data_manager.db.execute_query = MagicMock(
            return_value=[
                {"id": 1, "display_name": "Sub1", "is_channel": True},
                {"id": 2, "display_name": "Sub2", "is_channel": False},
            ]
        )
        subscribers = self.data_manager.get_all_subscribers()
        self.assertEqual(len(subscribers), 2)
        self.assertIn(Subscriber(1, "Sub1", True), subscribers)
        self.assertIn(Subscriber(2, "Sub2", False), subscribers)

    def test_save_subscriber(self):
        """Test saving a subscriber to the database."""
        subscriber = Subscriber(1, "Sub1", True)
        self.data_manager.db.execute_update = MagicMock()
        self.data_manager.save_subscriber(subscriber)
        self.data_manager.db.execute_update.assert_called_once_with(
            "INSERT OR REPLACE INTO subscribers (id, display_name, is_channel) VALUES (?, ?, ?)",  # noqa: E501
            (1, "Sub1", True),
        )

    def test_delete_subscriber(self):
        """Test deleting a subscriber from the database."""
        subscriber = Subscriber(1, "Sub1", True)
        self.data_manager.db.execute_update = MagicMock()
        self.data_manager.delete_subscriber(subscriber)
        self.data_manager.db.execute_update.assert_called_once_with(
            "DELETE FROM subscribers WHERE id = ?", (1,)
        )


class TestDataManagerStats(unittest.TestCase):
    def setUp(self):
        """Set up a temporary in-memory database for testing."""
        self.db = Database(db_path=":memory:")
        self.data_manager = DataManager(self.db)
        self._populate_test_data()

    def tearDown(self):
        """Close the database connection after tests."""
        self.db.close()

    def _populate_test_data(self):
        """Populate the database with data for testing."""
        # Players
        self.db.execute_update(
            "INSERT INTO players (id, name) VALUES ('player1', 'Alice')"
        )
        self.db.execute_update(
            "INSERT INTO players (id, name) VALUES ('player2', 'Bob')"
        )
        self.db.execute_update(
            "INSERT INTO players (id, name) VALUES ('player3', 'Charlie')"
        )
        self.db.execute_update(
            "INSERT INTO players (id, name) VALUES ('player4', 'David')"
        )

        # Question
        self.db.execute_update(
            "INSERT INTO questions (id, question_hash, question_text, answer_text) VALUES (1, 'hash1', 'q1', 'a1')"
        )
        today = date.today()
        self.db.execute_update(
            "INSERT INTO daily_questions (id, question_id, sent_at) VALUES (1, 1, ?)",
            (today,),
        )

        # Guesses
        # Player 1: Correct on first try (before hint)
        self.db.execute_update(
            "INSERT INTO guesses (daily_question_id, player_id, guess_text, is_correct, guessed_at) VALUES (1, 'player1', 'a1', 1, '2025-11-18 10:00:00')"
        )
        # Player 2: Incorrect, then correct (before and after hint)
        self.db.execute_update(
            "INSERT INTO guesses (daily_question_id, player_id, guess_text, is_correct, guessed_at) VALUES (1, 'player2', 'wrong', 0, '2025-11-18 09:00:00')"
        )
        self.db.execute_update(
            "INSERT INTO guesses (daily_question_id, player_id, guess_text, is_correct, guessed_at) VALUES (1, 'player2', 'a1', 1, '2025-11-18 11:00:00')"
        )
        # Player 3: Only incorrect guesses (after hint)
        self.db.execute_update(
            "INSERT INTO guesses (daily_question_id, player_id, guess_text, is_correct, guessed_at) VALUES (1, 'player3', 'wrong', 0, '2025-11-18 12:00:00')"
        )
        self.db.execute_update(
            "INSERT INTO guesses (daily_question_id, player_id, guess_text, is_correct, guessed_at) VALUES (1, 'player3', 'another wrong', 0, '2025-11-18 12:05:00')"
        )
        self.db.execute_update(
            "INSERT INTO guesses (daily_question_id, player_id, guess_text, is_correct, guessed_at) VALUES (1, 'player3', 'the longest guess of them all', 0, '2025-11-18 12:10:00')"
        )
        # Player 4: Only correct guess (after hint)
        self.db.execute_update(
            "INSERT INTO guesses (daily_question_id, player_id, guess_text, is_correct, guessed_at) VALUES (1, 'player4', 'a1', 1, '2025-11-18 13:00:00')"
        )

        # Hint message
        self.db.execute_update(
            "INSERT INTO messages (direction, method, recipient_sender, content, status, timestamp) VALUES ('outgoing', 'discord', 'channel1', 'Hint for today''s question', 'reminder_message', '2025-11-18 10:30:00')"
        )

    def test_get_hint_sent_timestamp(self):
        """Test retrieving the hint timestamp."""
        timestamp = self.data_manager.get_hint_sent_timestamp(1)
        self.assertEqual(timestamp, "2025-11-18 10:30:00")

    def test_get_first_try_solvers(self):
        """Test retrieving first-try solvers."""
        solvers = self.data_manager.get_first_try_solvers(1)
        self.assertEqual(len(solvers), 3)
        solver_names = {s["name"] for s in solvers}
        self.assertIn("Alice", solver_names)
        self.assertIn("Bob", solver_names)
        self.assertIn("David", solver_names)

    def test_get_guess_counts_per_player(self):
        """Test getting guess counts per player."""
        counts = self.data_manager.get_guess_counts_per_player(1)
        self.assertEqual(len(counts), 4)
        # Order is by guess_count DESC
        counts_dict = {item["name"]: item["guess_count"] for item in counts}
        self.assertEqual(counts_dict["Charlie"], 3)
        self.assertEqual(counts_dict["Bob"], 2)
        self.assertEqual(counts_dict["Alice"], 1)
        self.assertEqual(counts_dict["David"], 1)

    def test_get_most_common_guesses(self):
        """Test getting most common incorrect guesses."""
        common_guesses = self.data_manager.get_most_common_guesses(1)
        self.assertEqual(len(common_guesses), 3)
        self.assertEqual(common_guesses[0]["guess_text"], "wrong")
        self.assertEqual(common_guesses[0]["count"], 2)

    def test_get_craziest_guess(self):
        """Test getting the craziest (longest) guess."""
        crazy_guess = self.data_manager.get_craziest_guess(1)
        self.assertIsNotNone(crazy_guess)
        self.assertEqual(crazy_guess["player_name"], "Charlie")
        self.assertEqual(crazy_guess["guess_text"], "the longest guess of them all")

    def test_get_solvers_before_hint(self):
        """Test getting solvers before the hint."""
        solvers = self.data_manager.get_solvers_before_hint(1)
        self.assertEqual(len(solvers), 1)
        self.assertEqual(solvers[0]["name"], "Alice")

    def test_get_solvers_after_hint(self):
        """Test getting solvers who only guessed after the hint."""
        solvers = self.data_manager.get_solvers_after_hint(1)
        self.assertEqual(len(solvers), 1)
        self.assertEqual(solvers[0]["name"], "David")


if __name__ == "__main__":
    unittest.main()
