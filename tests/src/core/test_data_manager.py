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
                    "pending_rest_multiplier": 0.0,
                }
            ]
        )
        player = self.data_manager.get_player("1")
        self.assertIsNotNone(player)
        self.assertEqual(player.name, "Alice")
        self.assertEqual(player.score, 42)
        self.assertEqual(player.pending_rest_multiplier, 0.0)

        # Test not found
        self.db.execute_query = MagicMock(return_value=[])
        player = self.data_manager.get_player("999")
        self.assertIsNone(player)

    def test_create_player(self):
        """Test creating a new player."""
        self.db.execute_update = MagicMock()
        self.data_manager.create_player("1", "Alice")
        self.db.execute_update.assert_called_once_with(
            "INSERT INTO players (id, name, score, answer_streak) VALUES (?, ?, 0, 0)",
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

    def test_set_pending_multiplier(self):
        """Test setting a player's pending rest multiplier."""
        self.db.execute_update = MagicMock()
        self.data_manager.set_pending_multiplier("1", 1.2)
        self.db.execute_update.assert_called_once_with(
            "UPDATE players SET pending_rest_multiplier = ? WHERE id = ?", (1.2, "1")
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
                "pending_rest_multiplier": 1.2,
            },
            {
                "id": "2",
                "name": "Bob",
                "score": 0,
                "answer_streak": 0,
                "pending_rest_multiplier": 0.0,
            },
        ]
        players = self.data_manager.load_players()
        self.assertEqual(players["1"].name, "Alice")
        self.assertEqual(players["1"].score, 42)
        self.assertEqual(players["1"].answer_streak, 3)
        self.assertEqual(players["1"].pending_rest_multiplier, 1.2)
        self.assertEqual(players["2"].pending_rest_multiplier, 0.0)

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

    def test_update_daily_question_hint(self):
        """Test updating the hint for a daily question."""
        question = Question(
            category="TESTING",
            clue_value=100,
            question="What is a test?",
            answer="A trial",
            data_source="test",
            hint="Original hint",
            metadata={},
        )
        daily_q_id = self.data_manager.log_daily_question(question)

        # Update the hint
        new_hint = "Updated hint from Gemini"
        self.data_manager.update_daily_question_hint(daily_q_id, new_hint)

        # Verify hint was updated in questions table
        question_from_db = self.db.execute_query(
            "SELECT hint_text FROM questions WHERE question_text = 'What is a test?'"
        )
        self.assertEqual(len(question_from_db), 1)
        self.assertEqual(question_from_db[0]["hint_text"], new_hint)

    def test_update_daily_question_hint_invalid_id(self):
        """Test updating hint with invalid daily question ID."""
        # Should not raise an error, just log it
        self.data_manager.update_daily_question_hint(999, "Some hint")

        # No questions should have been updated
        question_from_db = self.db.execute_query(
            "SELECT * FROM questions WHERE hint_text = 'Some hint'"
        )
        self.assertEqual(len(question_from_db), 0)

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

    def test_mark_matching_guesses_as_correct(self):
        """Test marking previously incorrect guesses as correct based on a new answer."""
        # Log a daily question
        q = Question(
            question="What is 2+2?", answer="4", category="math", clue_value=100
        )
        daily_q_id = self.data_manager.log_daily_question(q)

        # Log several guesses (initially incorrect)
        self.data_manager.log_player_guess("p1", "Player1", daily_q_id, "four", False)
        self.data_manager.log_player_guess("p2", "Player2", daily_q_id, "5", False)
        self.data_manager.log_player_guess("p3", "Player3", daily_q_id, "FOUR", False)
        self.data_manager.log_player_guess("p4", "Player4", daily_q_id, "3", False)

        # Define a simple match function (case-insensitive exact match)
        def match_func(guess: str, answer: str) -> bool:
            return guess.lower() == answer.lower()

        # Mark guesses matching "four" as correct
        num_updated = self.data_manager.mark_matching_guesses_as_correct(
            daily_q_id, "four", match_func
        )

        # Should have updated 2 guesses (p1 and p3)
        self.assertEqual(num_updated, 2)

        # Verify the database state
        all_guesses = self.db.execute_query(
            "SELECT player_id, guess_text, is_correct FROM guesses WHERE daily_question_id = ? ORDER BY player_id",
            (daily_q_id,),
        )

        self.assertEqual(len(all_guesses), 4)
        self.assertEqual(all_guesses[0]["player_id"], "p1")
        self.assertEqual(all_guesses[0]["is_correct"], 1)  # Now correct
        self.assertEqual(all_guesses[1]["player_id"], "p2")
        self.assertEqual(all_guesses[1]["is_correct"], 0)  # Still incorrect
        self.assertEqual(all_guesses[2]["player_id"], "p3")
        self.assertEqual(all_guesses[2]["is_correct"], 1)  # Now correct
        self.assertEqual(all_guesses[3]["player_id"], "p4")
        self.assertEqual(all_guesses[3]["is_correct"], 0)  # Still incorrect

    def test_mark_matching_guesses_no_matches(self):
        """Test that marking guesses returns 0 when no guesses match."""
        # Log a daily question
        q = Question(
            question="What is 2+2?", answer="4", category="math", clue_value=100
        )
        daily_q_id = self.data_manager.log_daily_question(q)

        # Log some incorrect guesses
        self.data_manager.log_player_guess("p1", "Player1", daily_q_id, "5", False)
        self.data_manager.log_player_guess("p2", "Player2", daily_q_id, "3", False)

        # Define a match function
        def match_func(guess: str, answer: str) -> bool:
            return guess.lower() == answer.lower()

        # Try to mark guesses matching "seven" as correct (no matches)
        num_updated = self.data_manager.mark_matching_guesses_as_correct(
            daily_q_id, "seven", match_func
        )

        # Should have updated 0 guesses
        self.assertEqual(num_updated, 0)

        # Verify all guesses are still incorrect
        all_guesses = self.db.execute_query(
            "SELECT is_correct FROM guesses WHERE daily_question_id = ?", (daily_q_id,)
        )
        for guess in all_guesses:
            self.assertEqual(guess["is_correct"], 0)

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
        self.data_manager._db.execute_query = lambda query, params: [
            {"player_id": "123"},
            {"player_id": "456"},
        ]
        player_ids = self.data_manager.get_player_ids_with_role(role_name)
        self.assertEqual(player_ids, {"123", "456"})

        # Test with no results
        self.data_manager._db.execute_query = lambda query, params: []
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
        self.data_manager._db.execute_query = MagicMock(return_value=[])
        self.data_manager._db.execute_update = MagicMock(return_value=(None, 1))

        self.data_manager.assign_role_to_player(player_id, role_name)

        # Verify role was created and assigned
        self.assertEqual(self.data_manager._db.execute_update.call_count, 2)

    def test_clear_player_roles(self):
        """Test clearing all player roles."""
        # Mock DB method
        self.data_manager._db.execute_update = MagicMock(return_value=(None, 1))
        self.data_manager.clear_player_roles()
        self.assertEqual(self.data_manager._db.execute_update.call_count, 1)

    def test_get_all_subscribers(self):
        """Test getting all subscribers from the database."""
        self.data_manager._db.execute_query = MagicMock(
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
        self.data_manager._db.execute_update = MagicMock()
        self.data_manager.save_subscriber(subscriber)
        self.data_manager._db.execute_update.assert_called_once_with(
            "INSERT OR REPLACE INTO subscribers (id, display_name, is_channel) VALUES (?, ?, ?)",  # noqa: E501
            (1, "Sub1", True),
        )

    def test_delete_subscriber(self):
        """Test deleting a subscriber from the database."""
        subscriber = Subscriber(1, "Sub1", True)
        self.data_manager._db.execute_update = MagicMock()
        self.data_manager.delete_subscriber(subscriber)
        self.data_manager._db.execute_update.assert_called_once_with(
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
        self.data_manager._db.execute_query = MagicMock(
            return_value=[
                {
                    "id": "1",
                    "name": "Alice",
                    "score": 10,
                    "answer_streak": 2,
                    "pending_rest_multiplier": 0.0,
                }
            ]
        )
        players = self.data_manager.get_all_players()
        self.assertEqual(len(players), 1)
        self.assertEqual(players["1"].name, "Alice")

    def test_adjust_player_score(self):
        """Test adjusting a player's score directly in the database."""
        self.data_manager._db.execute_update = MagicMock()
        self.data_manager.adjust_player_score("player1", 50)
        self.data_manager._db.execute_update.assert_called_once_with(
            "UPDATE players SET score = score + ? WHERE id = ?", (50, "player1")
        )

    def test_log_messaging_event_incoming_ignored(self):
        """Test that incoming messages are not logged."""
        self.data_manager._db.execute_update = MagicMock()
        self.data_manager.log_messaging_event(
            "incoming", "discord", "12345", "Hello", "success"
        )
        self.data_manager._db.execute_update.assert_not_called()

    def test_get_player_scores(self):
        """Test retrieving player scores ordered by score."""
        self.data_manager._db.execute_query = MagicMock(
            return_value=[
                {"id": "1", "name": "Alice", "score": 100},
                {"id": "2", "name": "Bob", "score": 50},
            ]
        )
        scores = self.data_manager.get_player_scores()
        self.assertEqual(len(scores), 2)
        self.assertEqual(scores[0]["score"], 100)
        self.assertEqual(scores[1]["score"], 50)

    def test_get_player_scores_excludes_inactive_players(self):
        """Test that get_player_scores excludes players who haven't guessed in 28 days."""
        # Create players
        self.db.execute_update(
            "INSERT INTO players (id, name, score) VALUES ('1', 'Alice', 100)"
        )
        self.db.execute_update(
            "INSERT INTO players (id, name, score) VALUES ('2', 'Bob', 50)"
        )
        self.db.execute_update(
            "INSERT INTO players (id, name, score) VALUES ('3', 'Charlie', 75)"
        )

        # Create a daily question
        self.db.execute_update(
            "INSERT INTO daily_questions (id, question_id, sent_at) VALUES (1, 1, date('now'))"
        )

        # Alice guessed today (active)
        self.db.execute_update(
            "INSERT INTO guesses (daily_question_id, player_id, guess_text, is_correct, guessed_at) "
            "VALUES (1, '1', 'answer', 1, datetime('now'))"
        )

        # Bob guessed 10 days ago (active)
        self.db.execute_update(
            "INSERT INTO guesses (daily_question_id, player_id, guess_text, is_correct, guessed_at) "
            "VALUES (1, '2', 'answer', 1, datetime('now', '-10 days'))"
        )

        # Charlie guessed 30 days ago (inactive)
        self.db.execute_update(
            "INSERT INTO guesses (daily_question_id, player_id, guess_text, is_correct, guessed_at) "
            "VALUES (1, '3', 'answer', 1, datetime('now', '-30 days'))"
        )

        scores = self.data_manager.get_player_scores()

        # Should only include Alice and Bob, not Charlie
        self.assertEqual(len(scores), 2)
        player_ids = [s["id"] for s in scores]
        self.assertIn("1", player_ids)  # Alice
        self.assertIn("2", player_ids)  # Bob
        self.assertNotIn("3", player_ids)  # Charlie (inactive)

    def test_get_player_streaks(self):
        """Test retrieving player streaks ordered by streak."""
        self.data_manager._db.execute_query = MagicMock(
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
        self.data_manager._db.execute_query = MagicMock(return_value=[])
        result = self.data_manager.get_question_by_id(999)
        self.assertIsNone(result)

    def test_get_question_by_id_found(self):
        """Test get_question_by_id returns a Question when found."""
        self.data_manager._db.execute_query = MagicMock(
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

        self.data_manager._db.execute_query = mock_query
        result = self.data_manager.get_todays_daily_question()
        self.assertIsNone(result)

    def test_assign_role_to_player_existing_role(self):
        """Test assigning an existing role to a player."""

        def mock_query(query, params=None):
            if "SELECT id FROM roles" in query:
                return [{"id": 5}]  # Existing role found
            return []

        self.data_manager._db.execute_query = mock_query
        self.data_manager._db.execute_update = MagicMock()

        self.data_manager.assign_role_to_player("player1", "Existing Role")

        # Should only call execute_update once (to assign role, not create it)
        self.assertEqual(self.data_manager._db.execute_update.call_count, 1)

    def test_get_most_recent_daily_question(self):
        """Test retrieving the most recent daily question."""
        from datetime import date, timedelta

        # Mock database to return a daily question from yesterday
        yesterday = date.today() - timedelta(days=1)

        def mock_query(query, params=None):
            if "daily_questions" in query and "ORDER BY id DESC" in query:
                return [{"id": 5, "question_id": 10, "sent_at": yesterday.isoformat()}]
            elif "questions" in query and "id = ?" in query:
                return [
                    {
                        "question_text": "Test Q",
                        "answer_text": "Test A",
                        "category": "Test Cat",
                        "value": 100,
                        "source": "test",
                        "hint_text": "Test Hint",
                    }
                ]
            return []

        self.data_manager._db.execute_query = mock_query
        result = self.data_manager.get_most_recent_daily_question()

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 3)  # question, id, date
        question, daily_question_id, sent_date = result
        self.assertEqual(question.question, "Test Q")
        self.assertEqual(daily_question_id, 5)
        self.assertEqual(sent_date, yesterday)

    def test_get_most_recent_daily_question_no_questions(self):
        """Test get_most_recent_daily_question returns None when no questions exist."""
        self.data_manager._db.execute_query = MagicMock(return_value=[])
        result = self.data_manager.get_most_recent_daily_question()
        self.assertIsNone(result)

    def test_get_most_recent_daily_question_question_not_found(self):
        """Test get_most_recent_daily_question returns None when question record is missing."""
        from datetime import date

        def mock_query(query, params=None):
            if "daily_questions" in query:
                return [
                    {"id": 1, "question_id": 999, "sent_at": date.today().isoformat()}
                ]
            return []  # Question not found

        self.data_manager._db.execute_query = mock_query
        result = self.data_manager.get_most_recent_daily_question()
        self.assertIsNone(result)


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

        # Morning message
        self.db.execute_update(
            "INSERT INTO messages (direction, method, recipient_sender, content, status, timestamp) VALUES ('outgoing', 'discord', 'channel1', 'Morning question', 'morning_message', '2025-11-18 08:00:00')"
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
        self.assertEqual(len(solvers), 2)
        solver_names = {s["name"] for s in solvers}
        self.assertIn("Alice", solver_names)
        self.assertNotIn("Bob", solver_names)
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


class TestDataManagerTimezone(unittest.TestCase):
    def setUp(self):
        self.db = Database(db_path=":memory:")
        self.data_manager = DataManager(self.db)

        # Setup question for 2023-10-27
        self.db.execute_update(
            "INSERT INTO questions (id, question_hash, question_text, answer_text) VALUES (1, 'hash1', 'q1', 'a1')"
        )
        self.db.execute_update(
            "INSERT INTO daily_questions (id, question_id, sent_at) VALUES (1, 1, '2023-10-27')"
        )

        # Morning message at 15:00 UTC (8 AM Pacific)
        self.db.execute_update(
            "INSERT INTO messages (direction, method, recipient_sender, content, status, timestamp) VALUES ('outgoing', 'discord', 'channel1', 'Morning', 'morning_message', '2023-10-27 15:00:00')"
        )

    def tearDown(self):
        self.db.close()

    def test_hint_next_day_utc(self):
        # Hint sent at 02:00 UTC next day (19:00 Pacific same day)
        self.db.execute_update(
            "INSERT INTO messages (direction, method, recipient_sender, content, status, timestamp) VALUES ('outgoing', 'discord', 'channel1', 'Hint', 'reminder_message', '2023-10-28 02:00:00')"
        )

        timestamp = self.data_manager.get_hint_sent_timestamp(1)
        self.assertEqual(timestamp, "2023-10-28 02:00:00")

    def test_ignore_yesterday_hint(self):
        # Yesterday's hint at 02:00 UTC (same day as sent_at)
        self.db.execute_update(
            "INSERT INTO messages (direction, method, recipient_sender, content, status, timestamp) VALUES ('outgoing', 'discord', 'channel1', 'Yesterday Hint', 'reminder_message', '2023-10-27 02:00:00')"
        )

        # Today's hint at 02:00 UTC next day
        self.db.execute_update(
            "INSERT INTO messages (direction, method, recipient_sender, content, status, timestamp) VALUES ('outgoing', 'discord', 'channel1', 'Today Hint', 'reminder_message', '2023-10-28 02:00:00')"
        )

        timestamp = self.data_manager.get_hint_sent_timestamp(1)
        self.assertEqual(timestamp, "2023-10-28 02:00:00")


class TestSnapshot(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.data_manager = DataManager(self.db)
        self.data_manager.initialize_database()

    def tearDown(self):
        self.db.close()

    def test_snapshot_creation_and_retrieval(self):
        # 1. Create some players
        self.data_manager.create_player("p1", "Player 1")
        self.data_manager.create_player("p2", "Player 2")

        # Set some scores/streaks
        self.data_manager.adjust_player_score("p1", 100)
        self.data_manager.set_streak("p1", 5)

        self.data_manager.adjust_player_score("p2", 50)
        self.data_manager.set_streak("p2", 2)

        # 2. Create a question
        q = Question(
            question="What is 2+2?",
            answer="4",
            category="Math",
            clue_value=10,
            data_source="test",
            hint="Use your fingers",
        )

        # 3. Log daily question (should trigger snapshot)
        dq_id = self.data_manager.log_daily_question(q)
        self.assertIsNotNone(dq_id)

        # 4. Verify snapshot
        snapshot = self.data_manager.get_daily_snapshot(dq_id)

        self.assertIn("p1", snapshot)
        self.assertIn("p2", snapshot)

        p1 = snapshot["p1"]
        self.assertEqual(p1.score, 100)
        self.assertEqual(p1.answer_streak, 5)
        self.assertEqual(p1.name, "Player 1")

        p2 = snapshot["p2"]
        self.assertEqual(p2.score, 50)
        self.assertEqual(p2.answer_streak, 2)
        self.assertEqual(p2.name, "Player 2")

        # 5. Modify current state
        self.data_manager.adjust_player_score("p1", 10)  # p1 score becomes 110

        # 6. Verify snapshot is unchanged
        snapshot_again = self.data_manager.get_daily_snapshot(dq_id)
        self.assertEqual(snapshot_again["p1"].score, 100)

        # 7. Verify current state is changed
        current_p1 = self.data_manager.get_player("p1")
        self.assertEqual(current_p1.score, 110)


class TestDataManagerIntegration(unittest.TestCase):
    """Integration tests using real database with proper schema."""

    def setUp(self):
        """Set up a real in-memory database with the actual schema."""
        self.db = Database(":memory:")
        self.data_manager = DataManager(self.db)
        self.data_manager.initialize_database()

    def tearDown(self):
        """Clean up after tests."""
        self.db.close()

    def test_get_recent_answers(self):
        """Test retrieving recent answers from daily questions."""
        from datetime import timedelta

        # Create questions with proper schema columns
        q1 = Question("Q1?", "Answer1", "Cat", 100, "test", "Hint1")
        q2 = Question("Q2?", "Answer2", "Cat", 200, "test", "Hint2")
        q3 = Question("Q3?", "Answer3", "Cat", 300, "test", "Hint3")

        # Log them as daily questions with different dates
        # We need to manually insert into daily_questions to simulate different days
        # First, add questions to questions table
        for q in [q1, q2, q3]:
            self.data_manager.log_daily_question(q, mark_as_used_only=True)

        # Get question IDs
        query = "SELECT id, question_hash FROM questions ORDER BY id"
        questions = self.db.execute_query(query)

        # Insert daily questions for different dates
        today = date.today()
        for i, q_record in enumerate(questions):
            day_offset = -i  # Most recent first
            sent_date = today + timedelta(days=day_offset)
            self.db.execute_update(
                "INSERT INTO daily_questions (question_id, sent_at) VALUES (?, ?)",
                (q_record["id"], sent_date),
            )

        # Get recent answers
        recent = self.data_manager.get_recent_answers(limit=2)
        self.assertEqual(len(recent), 2)
        # Most recent first
        self.assertEqual(recent[0], "Answer1")  # Today
        self.assertEqual(recent[1], "Answer2")  # Yesterday

        # Get all
        all_recent = self.data_manager.get_recent_answers(limit=10)
        self.assertEqual(len(all_recent), 3)

    def test_get_used_question_hashes(self):
        """Test retrieving used question hashes."""
        q1 = Question("Q1?", "Answer1", "Cat", 100, "test", "Hint1")
        q2 = Question("Q2?", "Answer2", "Cat", 200, "test", "Hint2")

        # Initially empty
        hashes = self.data_manager.get_used_question_hashes()
        self.assertEqual(len(hashes), 0)

        # Log questions
        self.data_manager.log_daily_question(q1)
        self.data_manager.log_daily_question(q2)

        # Check hashes are tracked
        hashes = self.data_manager.get_used_question_hashes()
        self.assertEqual(len(hashes), 2)
        self.assertIn(str(q1.id), hashes)
        self.assertIn(str(q2.id), hashes)

    def test_alternative_answers(self):
        """Test adding and retrieving alternative answers."""
        # Create and log a question
        q = Question("Q?", "Original", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)

        # Get the question_id from the database
        query = "SELECT question_id FROM daily_questions WHERE id = ?"
        result = self.db.execute_query(query, (dq_id,))
        question_id = result[0]["question_id"]

        # Initially no alternative answers
        alts = self.data_manager.get_alternative_answers(question_id)
        self.assertEqual(len(alts), 0)

        # Add alternative answers
        self.data_manager.add_alternative_answer(question_id, "Alt1", "admin1")
        self.data_manager.add_alternative_answer(question_id, "Alt2", "admin1")

        # Retrieve them
        alts = self.data_manager.get_alternative_answers(question_id)
        self.assertEqual(len(alts), 2)
        self.assertIn("Alt1", alts)
        self.assertIn("Alt2", alts)

    def test_powerup_usage_tracking(self):
        """Test logging and retrieving powerup usage."""
        # Create a question
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)

        # Get question_id
        query = "SELECT question_id FROM daily_questions WHERE id = ?"
        result = self.db.execute_query(query, (dq_id,))
        question_id = result[0]["question_id"]

        # Create players
        self.data_manager.create_player("p1", "Player1")
        self.data_manager.create_player("p2", "Player2")

        # Log powerup usages
        self.data_manager.log_powerup_usage("p1", "shield", question_id=question_id)
        self.data_manager.log_powerup_usage(
            "p2", "attack", target_user_id="p1", question_id=question_id
        )

        # Retrieve usage for question
        usages = self.data_manager.get_powerup_usages_for_question(question_id)
        self.assertEqual(len(usages), 2)

        # Check details
        shield_usage = [u for u in usages if u["powerup_type"] == "shield"][0]
        self.assertEqual(shield_usage["user_id"], "p1")

        attack_usage = [u for u in usages if u["powerup_type"] == "attack"][0]
        self.assertEqual(attack_usage["user_id"], "p2")
        self.assertEqual(attack_usage["target_user_id"], "p1")

    def test_score_adjustment_logging(self):
        """Test logging score adjustments."""
        # Create players
        self.data_manager.create_player("p1", "Player1")
        self.data_manager.create_player("admin1", "Admin1")

        # Log adjustment
        self.data_manager.log_score_adjustment("p1", "admin1", 50, "Test adjustment")

        # Verify in database
        query = "SELECT * FROM score_adjustments WHERE player_id = ?"
        result = self.db.execute_query(query, ("p1",))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["amount"], 50)
        self.assertEqual(result[0]["admin_id"], "admin1")
        self.assertEqual(result[0]["reason"], "Test adjustment")

    def test_mark_matching_guesses_as_correct(self):
        """Test marking guesses as correct when alternative answer is added."""
        # Create question and daily question
        q = Question("Q?", "correct", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)

        # Create players
        self.data_manager.create_player("p1", "Player1")
        self.data_manager.create_player("p2", "Player2")
        self.data_manager.create_player("p3", "Player3")

        # Log guesses
        self.data_manager.log_player_guess("p1", "Player1", dq_id, "correct", True)
        self.data_manager.log_player_guess("p2", "Player2", dq_id, "right", False)
        self.data_manager.log_player_guess("p3", "Player3", dq_id, "wrong", False)

        # Simple match function
        def simple_match(guess: str, answer: str) -> bool:
            return guess.lower().strip() == answer.lower().strip()

        # Mark "right" as correct
        count = self.data_manager.mark_matching_guesses_as_correct(
            dq_id, "right", simple_match
        )
        self.assertEqual(count, 1)

        # Verify guess is now correct
        query = "SELECT is_correct FROM guesses WHERE player_id = ?"
        result = self.db.execute_query(query, ("p2",))
        self.assertEqual(result[0]["is_correct"], 1)

        # p3's guess should still be incorrect
        result = self.db.execute_query(query, ("p3",))
        self.assertEqual(result[0]["is_correct"], 0)

    def test_get_last_correct_guess_date(self):
        """Test retrieving the date of a player's last correct guess."""
        # Create player
        self.data_manager.create_player("p1", "Player1")

        # No guesses yet
        last_date = self.data_manager.get_last_correct_guess_date("p1")
        self.assertIsNone(last_date)

        # Create a question
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)

        # Make a correct guess
        self.data_manager.log_player_guess("p1", "Player1", dq_id, "A", True)

        # Check the date
        last_date = self.data_manager.get_last_correct_guess_date("p1")
        self.assertIsNotNone(last_date)
        # Use DataManager's timezone-aware date instead of system date
        self.assertEqual(last_date, self.data_manager.get_today())

    def test_get_correct_guess_count(self):
        """Test counting correct guesses for a daily question."""
        # Create question
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)

        # Create players
        self.data_manager.create_player("p1", "Player1")
        self.data_manager.create_player("p2", "Player2")
        self.data_manager.create_player("p3", "Player3")

        # Initially 0
        count = self.data_manager.get_correct_guess_count(dq_id)
        self.assertEqual(count, 0)

        # Add guesses
        self.data_manager.log_player_guess("p1", "Player1", dq_id, "A", True)
        self.data_manager.log_player_guess("p2", "Player2", dq_id, "B", False)
        self.data_manager.log_player_guess("p3", "Player3", dq_id, "A", True)

        # Check count
        count = self.data_manager.get_correct_guess_count(dq_id)
        self.assertEqual(count, 2)

    def test_reset_unanswered_streaks(self):
        """Test resetting streaks for players who didn't answer correctly."""
        # Create players with streaks
        self.data_manager.create_player("p1", "Player1")
        self.data_manager.create_player("p2", "Player2")
        self.data_manager.create_player("p3", "Player3")

        self.data_manager.set_streak("p1", 5)
        self.data_manager.set_streak("p2", 3)
        self.data_manager.set_streak("p3", 0)

        # Create question
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)

        # Only p1 answers correctly
        self.data_manager.log_player_guess("p1", "Player1", dq_id, "A", True)
        self.data_manager.log_player_guess("p2", "Player2", dq_id, "B", False)

        # Reset unanswered streaks
        self.data_manager.reset_unanswered_streaks(dq_id)

        # Check streaks
        p1 = self.data_manager.get_player("p1")
        p2 = self.data_manager.get_player("p2")
        p3 = self.data_manager.get_player("p3")

        self.assertEqual(p1.answer_streak, 5)  # Unchanged (answered correctly)
        self.assertEqual(p2.answer_streak, 0)  # Reset (didn't answer correctly)
        self.assertEqual(p3.answer_streak, 0)  # Already 0

    def test_get_guesses_for_daily_question(self):
        """Test retrieving all guesses for a daily question."""
        # Create question
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)

        # Create players and log guesses
        self.data_manager.create_player("p1", "Player1")
        self.data_manager.create_player("p2", "Player2")

        self.data_manager.log_player_guess("p1", "Player1", dq_id, "A", True)
        self.data_manager.log_player_guess("p2", "Player2", dq_id, "B", False)
        self.data_manager.log_player_guess("p1", "Player1", dq_id, "C", False)

        # Get all guesses
        guesses = self.data_manager.get_guesses_for_daily_question(dq_id)
        self.assertEqual(len(guesses), 3)

        # Verify order (chronological)
        self.assertEqual(guesses[0]["player_id"], "p1")
        self.assertEqual(guesses[0]["guess_text"], "A")
        self.assertEqual(guesses[0]["is_correct"], 1)

    def test_get_first_try_solvers(self):
        """Test identifying players who solved on first try."""
        # Create question
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)

        # Create players
        self.data_manager.create_player("p1", "Player1")
        self.data_manager.create_player("p2", "Player2")
        self.data_manager.create_player("p3", "Player3")

        # p1: correct on first try
        self.data_manager.log_player_guess("p1", "Player1", dq_id, "A", True)

        # p2: correct after multiple tries
        self.data_manager.log_player_guess("p2", "Player2", dq_id, "B", False)
        self.data_manager.log_player_guess("p2", "Player2", dq_id, "A", True)

        # p3: never correct
        self.data_manager.log_player_guess("p3", "Player3", dq_id, "B", False)

        # Get first-try solvers
        solvers = self.data_manager.get_first_try_solvers(dq_id)
        self.assertEqual(len(solvers), 1)
        self.assertEqual(solvers[0]["id"], "p1")

    def test_get_guess_counts_per_player(self):
        """Test counting unique guesses per player."""
        # Create question
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)

        # Create players
        self.data_manager.create_player("p1", "Player1")
        self.data_manager.create_player("p2", "Player2")

        # p1 makes 3 unique guesses
        self.data_manager.log_player_guess("p1", "Player1", dq_id, "A", False)
        self.data_manager.log_player_guess("p1", "Player1", dq_id, "B", False)
        self.data_manager.log_player_guess("p1", "Player1", dq_id, "C", True)

        # p2 makes 1 guess
        self.data_manager.log_player_guess("p2", "Player2", dq_id, "A", True)

        # Get counts
        counts = self.data_manager.get_guess_counts_per_player(dq_id)
        self.assertEqual(len(counts), 2)

        # Ordered by count descending
        self.assertEqual(counts[0]["name"], "Player1")
        self.assertEqual(counts[0]["guess_count"], 3)
        self.assertEqual(counts[1]["name"], "Player2")
        self.assertEqual(counts[1]["guess_count"], 1)

    def test_get_most_common_guesses(self):
        """Test finding most common incorrect guesses."""
        # Create question
        q = Question("Q?", "correct", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)

        # Create players
        for i in range(5):
            self.data_manager.create_player(f"p{i}", f"Player{i}")

        # Multiple people guess "wrong1"
        self.data_manager.log_player_guess("p0", "Player0", dq_id, "wrong1", False)
        self.data_manager.log_player_guess("p1", "Player1", dq_id, "wrong1", False)
        self.data_manager.log_player_guess("p2", "Player2", dq_id, "wrong1", False)

        # Some guess "wrong2"
        self.data_manager.log_player_guess("p3", "Player3", dq_id, "wrong2", False)
        self.data_manager.log_player_guess("p4", "Player4", dq_id, "wrong2", False)

        # Get common guesses
        common = self.data_manager.get_most_common_guesses(dq_id)
        self.assertGreaterEqual(len(common), 2)

        # Most common first
        self.assertEqual(common[0]["guess_text"], "wrong1")
        self.assertEqual(common[0]["count"], 3)
        self.assertEqual(common[1]["guess_text"], "wrong2")
        self.assertEqual(common[1]["count"], 2)

    def test_get_craziest_guess(self):
        """Test finding the longest/craziest guess."""
        # Create question
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)

        # Create players
        self.data_manager.create_player("p1", "Player1")
        self.data_manager.create_player("p2", "Player2")

        # Make guesses of different lengths
        self.data_manager.log_player_guess("p1", "Player1", dq_id, "short", False)
        self.data_manager.log_player_guess(
            "p2", "Player2", dq_id, "this is a very long guess", False
        )

        # Get craziest
        craziest = self.data_manager.get_craziest_guess(dq_id)
        self.assertIsNotNone(craziest)
        self.assertEqual(craziest["player_name"], "Player2")
        self.assertEqual(craziest["guess_text"], "this is a very long guess")

    def test_mark_guess_as_correct(self):
        """Test manually marking a specific guess as correct."""
        # Create question
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)

        # Create player and make incorrect guess
        self.data_manager.create_player("p1", "Player1")
        self.data_manager.log_player_guess("p1", "Player1", dq_id, "B", False)

        # Get the guess ID
        query = "SELECT id FROM guesses WHERE player_id = ?"
        result = self.db.execute_query(query, ("p1",))
        guess_id = result[0]["id"]

        # Mark as correct
        self.data_manager.mark_guess_as_correct(guess_id)

        # Verify
        query = "SELECT is_correct FROM guesses WHERE id = ?"
        result = self.db.execute_query(query, (guess_id,))
        self.assertEqual(result[0]["is_correct"], 1)

    def test_clear_stale_rest_multipliers(self):
        """Stale multipliers (no rest today) are cleared; today's rest multiplier is preserved."""
        from data.readers.question import Question

        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)

        self.data_manager.create_player("p1", "Player1")  # stale multiplier
        self.data_manager.create_player("p2", "Player2")  # rested today
        self.data_manager.create_player("p3", "Player3")  # no multiplier

        # p1 has a leftover multiplier from a prior day (no powerup_usage row for this question)
        self.data_manager.set_pending_multiplier("p1", 1.2)
        # p2 rested today
        self.data_manager.set_pending_multiplier("p2", 1.2)
        self.data_manager.log_powerup_usage("p2", "rest", None, dq_id)

        self.data_manager.clear_stale_rest_multipliers(dq_id)

        self.assertEqual(self.data_manager.get_pending_multiplier("p1"), 0.0)
        self.assertEqual(self.data_manager.get_pending_multiplier("p2"), 1.2)
        self.assertEqual(self.data_manager.get_pending_multiplier("p3"), 0.0)


if __name__ == "__main__":
    unittest.main()
