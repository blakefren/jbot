import unittest
from unittest.mock import patch, MagicMock
from datetime import date

from src.core.data_manager import DataManager
from src.core.player import Player
from src.core.subscriber import Subscriber
from data.readers.question import Question
from db.database import Database


class TestDataManager(unittest.TestCase):
    def test_get_player(self):
        """Test retrieving a single player."""
        self.db.execute_query = MagicMock(
            return_value=[
                {
                    "id": "1",
                    "name": "Alice",
                    "score": 42,
                    "answer_streak": 3,
                    "active_shield": 1,
                }
            ]
        )
        player = self.data_manager.get_player("1")
        self.assertIsNotNone(player)
        self.assertEqual(player.name, "Alice")
        self.assertEqual(player.score, 42)
        self.assertTrue(player.active_shield)

        # Test not found
        self.db.execute_query = MagicMock(return_value=[])
        player = self.data_manager.get_player("999")
        self.assertIsNone(player)

    def test_create_player(self):
        """Test creating a new player."""
        self.db.execute_update = MagicMock()
        self.data_manager.create_player("1", "Alice")
        self.db.execute_update.assert_called_once_with(
            "INSERT INTO players (id, name, score, answer_streak, active_shield) VALUES (?, ?, 0, 0, 0)",
            ("1", "Alice"),
        )

    def test_update_player_name(self):
        """Test updating a player's name."""
        self.db.execute_update = MagicMock()
        self.data_manager.update_player_name("1", "New Name")
        self.db.execute_update.assert_called_once_with(
            "UPDATE players SET name = ? WHERE id = ?", ("New Name", "1")
        )

    def test_increment_streak(self):
        """Test incrementing a player's streak."""
        self.db.execute_update = MagicMock()
        self.data_manager.increment_streak("1")
        self.db.execute_update.assert_called_once_with(
            "UPDATE players SET answer_streak = answer_streak + 1 WHERE id = ?", ("1",)
        )

    def test_reset_streak(self):
        """Test resetting a player's streak."""
        self.db.execute_update = MagicMock()
        self.data_manager.reset_streak("1")
        self.db.execute_update.assert_called_once_with(
            "UPDATE players SET answer_streak = 0 WHERE id = ?", ("1",)
        )

    def test_set_shield(self):
        """Test setting a player's shield status."""
        self.db.execute_update = MagicMock()
        self.data_manager.set_shield("1", True)
        self.db.execute_update.assert_called_once_with(
            "UPDATE players SET active_shield = ? WHERE id = ?", (True, "1")
        )

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

    def test_initialize_database(self):
        """Test that initialize_database reads and executes the schema."""
        with patch("builtins.open", MagicMock()) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = (
                "CREATE TABLE test (id INTEGER);"
            )
            mock_db = MagicMock()
            dm = DataManager(mock_db)
            dm.initialize_database()
            mock_db.execute_script.assert_called_once_with(
                "CREATE TABLE test (id INTEGER);"
            )

    def test_get_all_players(self):
        """Test get_all_players delegates to load_players."""
        self.data_manager.db.execute_query = MagicMock(
            return_value=[
                {
                    "id": "1",
                    "name": "Alice",
                    "score": 10,
                    "answer_streak": 2,
                    "active_shield": 1,
                }
            ]
        )
        players = self.data_manager.get_all_players()
        self.assertEqual(len(players), 1)
        self.assertEqual(players["1"].name, "Alice")

    def test_adjust_player_score(self):
        """Test adjusting a player's score directly in the database."""
        self.data_manager.db.execute_update = MagicMock()
        self.data_manager.adjust_player_score("player1", 50)
        self.data_manager.db.execute_update.assert_called_once_with(
            "UPDATE players SET score = score + ? WHERE id = ?", (50, "player1")
        )

    def test_log_messaging_event_incoming_ignored(self):
        """Test that incoming messages are not logged."""
        self.data_manager.db.execute_update = MagicMock()
        self.data_manager.log_messaging_event(
            "incoming", "discord", "12345", "Hello", "success"
        )
        self.data_manager.db.execute_update.assert_not_called()

    def test_get_player_scores(self):
        """Test retrieving player scores ordered by score."""
        self.data_manager.db.execute_query = MagicMock(
            return_value=[
                {"id": "1", "name": "Alice", "score": 100},
                {"id": "2", "name": "Bob", "score": 50},
            ]
        )
        scores = self.data_manager.get_player_scores()
        self.assertEqual(len(scores), 2)
        self.assertEqual(scores[0]["score"], 100)
        self.assertEqual(scores[1]["score"], 50)

    def test_get_player_streaks(self):
        """Test retrieving player streaks ordered by streak."""
        self.data_manager.db.execute_query = MagicMock(
            return_value=[
                {"id": "1", "name": "Alice", "answer_streak": 5},
                {"id": "2", "name": "Bob", "answer_streak": 3},
            ]
        )
        streaks = self.data_manager.get_player_streaks()
        self.assertEqual(len(streaks), 2)
        self.assertEqual(streaks[0]["answer_streak"], 5)
        self.assertEqual(streaks[1]["answer_streak"], 3)

    def test_get_question_by_id_not_found(self):
        """Test get_question_by_id returns None when not found."""
        self.data_manager.db.execute_query = MagicMock(return_value=[])
        result = self.data_manager.get_question_by_id(999)
        self.assertIsNone(result)

    def test_get_question_by_id_found(self):
        """Test get_question_by_id returns a Question when found."""
        self.data_manager.db.execute_query = MagicMock(
            return_value=[
                {
                    "id": 1,
                    "question_text": "Test Q",
                    "answer_text": "Test A",
                    "category": "Test Cat",
                    "value": 100,
                    "source": "test",
                    "hint_text": "Test Hint",
                }
            ]
        )
        result = self.data_manager.get_question_by_id(1)
        self.assertIsNotNone(result)
        self.assertEqual(result.question, "Test Q")
        self.assertEqual(result.answer, "Test A")

    def test_get_todays_daily_question_question_not_found(self):
        """Test get_todays_daily_question returns None when question record is missing."""

        # Mock to return a daily_question entry but no corresponding question
        def mock_query(query, params=None):
            if "daily_questions" in query:
                return [{"id": 1, "question_id": 999}]
            return []  # Question not found

        self.data_manager.db.execute_query = mock_query
        result = self.data_manager.get_todays_daily_question()
        self.assertIsNone(result)

    def test_assign_role_to_player_existing_role(self):
        """Test assigning an existing role to a player."""

        def mock_query(query, params=None):
            if "SELECT id FROM roles" in query:
                return [{"id": 5}]  # Existing role found
            return []

        self.data_manager.db.execute_query = mock_query
        self.data_manager.db.execute_update = MagicMock()

        self.data_manager.assign_role_to_player("player1", "Existing Role")

        # Should only call execute_update once (to assign role, not create it)
        self.assertEqual(self.data_manager.db.execute_update.call_count, 1)


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
        # Use a fixed date that matches the hard-coded guess and hint timestamps below
        # to make this test deterministic across different execution dates (e.g., CI servers).
        today = date(2025, 11, 18)
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


class TestDataManagerNoHint(unittest.TestCase):
    """Test cases for when there's no hint timestamp."""

    def setUp(self):
        """Set up a database without hint messages."""
        self.db = Database(db_path=":memory:")
        self.data_manager = DataManager(self.db)

        # Players
        self.db.execute_update(
            "INSERT INTO players (id, name) VALUES ('player1', 'Alice')"
        )

        # Question and daily question
        self.db.execute_update(
            "INSERT INTO questions (id, question_hash, question_text, answer_text) VALUES (1, 'hash1', 'q1', 'a1')"
        )
        today = date.today()
        self.db.execute_update(
            "INSERT INTO daily_questions (id, question_id, sent_at) VALUES (1, 1, ?)",
            (today,),
        )

        # No hint message inserted

    def tearDown(self):
        self.db.close()

    def test_get_solvers_before_hint_no_hint(self):
        """Test that get_solvers_before_hint returns empty list when no hint exists."""
        result = self.data_manager.get_solvers_before_hint(1)
        self.assertEqual(result, [])

    def test_get_solvers_after_hint_no_hint(self):
        """Test that get_solvers_after_hint returns empty list when no hint exists."""
        result = self.data_manager.get_solvers_after_hint(1)
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
