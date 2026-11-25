import unittest
from unittest.mock import patch, MagicMock
from datetime import date, timedelta

from src.core.data_manager import DataManager
from src.core.player import Player
from src.core.subscriber import Subscriber
from data.readers.question import Question
from db.database import Database


class TestDataManager(unittest.TestCase):
    def test_get_player(self):
        """Read persisted player fields and return None for an unknown ID."""
        self.data_manager.create_player("1", "Alice")
        self.data_manager.adjust_player_score("1", 42)
        self.data_manager.set_streak("1", 3)

        player = self.data_manager.get_player("1")
        self.assertEqual(
            (player.name, player.score, player.answer_streak), ("Alice", 42, 3)
        )
        self.assertEqual(player.pending_rest_multiplier, 0.0)
        self.assertIsNone(self.data_manager.get_player("999"))

    def test_create_player(self):
        """Create a player with the schema's default state."""
        self.data_manager.create_player("1", "Alice")
        player = self.data_manager.get_player("1")
        self.assertEqual(
            (player.name, player.score, player.answer_streak), ("Alice", 0, 0)
        )

    def test_update_player_name(self):
        """Persist a changed player name."""
        self.data_manager.create_player("1", "Alice")
        self.data_manager.update_player_name("1", "New Name")
        self.assertEqual(self.data_manager.get_player("1").name, "New Name")

    def test_increment_streak(self):
        """Increment a persisted streak."""
        self.data_manager.create_player("1", "Alice")
        self.data_manager.increment_streak("1")
        self.assertEqual(self.data_manager.get_player("1").answer_streak, 1)

    def test_reset_streak(self):
        """Reset a persisted streak."""
        self.data_manager.create_player("1", "Alice")
        self.data_manager.set_streak("1", 4)
        self.data_manager.reset_streak("1")
        self.assertEqual(self.data_manager.get_player("1").answer_streak, 0)

    def test_increment_pending_multiplier(self):
        """Accumulate a persisted rest multiplier."""
        self.data_manager.create_player("1", "Alice")
        self.data_manager.increment_pending_multiplier("1", 0.2)
        self.data_manager.increment_pending_multiplier("1", 0.3)
        self.assertAlmostEqual(self.data_manager.get_pending_multiplier("1"), 0.5)

    def test_load_players(self):
        """Load persisted players into the domain model."""
        self.data_manager.create_player("1", "Alice")
        self.data_manager.adjust_player_score("1", 42)
        self.data_manager.set_streak("1", 3)
        self.data_manager.increment_pending_multiplier("1", 1.2)
        self.data_manager.create_player("2", "Bob")

        players = self.data_manager.load_players()
        self.assertEqual(players["1"].name, "Alice")
        self.assertEqual(players["1"].score, 42)
        self.assertEqual(players["1"].answer_streak, 3)
        self.assertEqual(players["1"].pending_rest_multiplier, 1.2)
        self.assertEqual(players["2"].pending_rest_multiplier, 0.0)

    def setUp(self):
        """Set up for test cases."""
        self.db_path = ":memory:"
        self.db = Database(self.db_path)
        self.data_manager = DataManager(self.db)

    def tearDown(self):
        """Clean up after tests."""
        self.db.close()

    def test_backup_database_writes_restorable_copy(self):
        """backup_database() writes a copy of a file-backed database."""
        import os
        import tempfile

        with tempfile.TemporaryDirectory(dir=os.path.dirname(__file__)) as directory:
            source = Database(os.path.join(directory, "source.db"))
            backup_path = os.path.join(directory, "backup.db")
            restored = None
            try:
                source_manager = DataManager(source)
                source_manager.create_player("1", "Alice")
                source_manager.adjust_player_score("1", 42)

                source_manager.backup_database(backup_path)

                restored = Database(backup_path)
                player = DataManager(restored).get_player("1")
                self.assertEqual((player.name, player.score), ("Alice", 42))
            finally:
                source.close()
                if restored:
                    restored.close()

    def test_transaction_rolls_back_data_manager_operations(self):
        with self.assertRaisesRegex(RuntimeError, "abort action"):
            with self.data_manager.transaction():
                self.data_manager.create_player("rollback", "Rollback")
                raise RuntimeError("abort action")

        self.assertIsNone(self.data_manager.get_player("rollback"))

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
        """Resolve assigned roles from persisted relationships."""
        self.data_manager.create_player("123", "Alice")
        self.data_manager.create_player("456", "Bob")
        self.data_manager.assign_role_to_player("123", "Winner")
        self.data_manager.assign_role_to_player("456", "Winner")
        self.data_manager.assign_role_to_player("123", "Other")

        self.assertEqual(
            self.data_manager.get_player_ids_with_role("Winner"), {"123", "456"}
        )
        self.assertEqual(self.data_manager.get_player_ids_with_role("Missing"), set())

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

    def test_read_guess_history_orders_same_second_guesses_by_insertion(self):
        q = Question(question="q1", answer="a1", category="cat", clue_value=100)
        daily_id = self.data_manager.log_daily_question(q)
        for player_id in ("456", "123", "789"):
            self.data_manager.log_player_guess(
                player_id, f"P{player_id}", daily_id, "a1", True
            )
        self.data_manager._db.execute_update(
            "UPDATE guesses SET guessed_at = '2023-01-01 10:00:00'"
        )

        history = self.data_manager.read_guess_history()

        self.assertEqual([g["player_id"] for g in history], ["456", "123", "789"])

    def test_read_guess_history_with_daily_question_filter(self):
        """Test read_guess_history with daily_question_id filter."""
        # Create two daily questions on different dates
        q1 = Question(question="q1", answer="a1", category="cat", clue_value=100)
        q2 = Question(question="q2", answer="a2", category="cat", clue_value=100)
        daily_q1_id = self.data_manager.log_daily_question(q1)

        # To create a second daily question, we need to insert it manually with a different date
        # First, get the question_id for q2 by inserting and retrieving
        q2_id = self.data_manager._db.execute_query(
            "INSERT INTO questions (question_text, answer_text, category, value) VALUES (?, ?, ?, ?) "
            "RETURNING id",
            ("q2", "a2", "cat", 100),
        )[0]["id"]

        # Now insert a daily_question for q2 with a different date
        daily_q2_id = self.data_manager._db.execute_query(
            "INSERT INTO daily_questions (question_id, sent_at) VALUES (?, date('now', '+1 day')) "
            "RETURNING id",
            (q2_id,),
        )[0]["id"]

        # Log guesses for both questions
        self.data_manager.log_player_guess("123", "PlayerOne", daily_q1_id, "A1", True)
        self.data_manager.log_player_guess("123", "PlayerOne", daily_q2_id, "A2", True)
        self.data_manager.log_player_guess(
            "456", "PlayerTwo", daily_q1_id, "Wrong1", False
        )
        self.data_manager.log_player_guess(
            "456", "PlayerTwo", daily_q2_id, "Wrong2", False
        )

        # Test: get all guesses for player 123
        all_player_123 = self.data_manager.read_guess_history(user_id="123")
        self.assertEqual(len(all_player_123), 2)

        # Test: get guesses for player 123 on daily_q1 only
        q1_only = self.data_manager.read_guess_history(
            user_id="123", daily_question_id=daily_q1_id
        )
        self.assertEqual(len(q1_only), 1)
        self.assertEqual(q1_only[0]["guess_text"], "A1")
        self.assertEqual(q1_only[0]["daily_question_id"], daily_q1_id)

        # Test: get guesses for player 123 on daily_q2 only
        q2_only = self.data_manager.read_guess_history(
            user_id="123", daily_question_id=daily_q2_id
        )
        self.assertEqual(len(q2_only), 1)
        self.assertEqual(q2_only[0]["guess_text"], "A2")
        self.assertEqual(q2_only[0]["daily_question_id"], daily_q2_id)

        # Test: get all guesses for daily_q1 (all players)
        q1_all_players = self.data_manager.read_guess_history(
            daily_question_id=daily_q1_id
        )
        self.assertEqual(len(q1_all_players), 2)  # One from player 123, one from 456

        # Test: non-existent combination
        no_results = self.data_manager.read_guess_history(
            user_id="999", daily_question_id=daily_q1_id
        )
        self.assertEqual(len(no_results), 0)

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
        """Create a role and persist the player-role relationship."""
        player_id = "player1"
        role_name = "New Role"
        self.data_manager.create_player(player_id, "Player")
        self.data_manager.assign_role_to_player(player_id, role_name)
        rows = self.db.execute_query(
            "SELECT r.name FROM roles r JOIN player_roles pr ON pr.role_id = r.id "
            "WHERE pr.player_id = ?",
            (player_id,),
        )
        self.assertEqual([row["name"] for row in rows], [role_name])

    def test_clear_player_roles(self):
        """Remove persisted player-role relationships."""
        self.data_manager.create_player("player1", "Player")
        self.data_manager.assign_role_to_player("player1", "Role")
        self.data_manager.clear_player_roles()
        rows = self.db.execute_query("SELECT * FROM player_roles")
        self.assertEqual(rows, [])

    def test_get_all_subscribers(self):
        """Load subscribers saved through the data layer."""
        self.data_manager.save_subscriber(Subscriber("1", "Sub1", True))
        self.data_manager.save_subscriber(Subscriber("2", "Sub2", False))
        subscribers = self.data_manager.get_all_subscribers()
        self.assertEqual(len(subscribers), 2)
        self.assertIn(Subscriber("1", "Sub1", True), subscribers)
        self.assertIn(Subscriber("2", "Sub2", False), subscribers)

    def test_save_subscriber(self):
        """Persist a subscriber."""
        subscriber = Subscriber("1", "Sub1", True)
        self.data_manager.save_subscriber(subscriber)
        rows = self.db.execute_query("SELECT * FROM subscribers WHERE id = ?", ("1",))
        self.assertEqual(rows[0]["display_name"], "Sub1")

    def test_delete_subscriber(self):
        """Delete a persisted subscriber."""
        subscriber = Subscriber("1", "Sub1", True)
        self.data_manager.save_subscriber(subscriber)
        self.data_manager.delete_subscriber(subscriber)
        rows = self.db.execute_query("SELECT * FROM subscribers WHERE id = ?", ("1",))
        self.assertEqual(rows, [])

    def test_initialize_database(self):
        """initialize_database recreates missing tables from the real schema."""
        self.db.execute_script("DROP TABLE subscribers")

        self.data_manager.initialize_database()

        self.data_manager.save_subscriber(Subscriber("1", "Sub1", True))
        self.assertEqual(
            self.data_manager.get_all_subscribers(), {Subscriber("1", "Sub1", True)}
        )

    def test_get_all_players(self):
        """Return all persisted players keyed by ID."""
        self.data_manager.create_player("1", "Alice")
        self.data_manager.set_streak("1", 2)
        players = self.data_manager.get_all_players()
        self.assertEqual(len(players), 1)
        self.assertEqual(players["1"].name, "Alice")
        self.assertEqual(players["1"].answer_streak, 2)

    def test_adjust_player_score(self):
        """Persist a score adjustment."""
        self.data_manager.create_player("player1", "Player")
        self.data_manager.adjust_player_score("player1", 50)
        self.assertEqual(self.data_manager.get_player("player1").score, 50)

    def test_log_messaging_event_incoming_ignored(self):
        """Test that incoming messages are not logged."""
        self.data_manager.log_messaging_event(
            "incoming", "discord", "12345", "Hello", "success"
        )
        self.assertEqual(self.db.execute_query("SELECT * FROM messages"), [])

    def test_get_player_scores(self):
        """Return active players ordered by their persisted scores."""
        self.data_manager.create_player("1", "Alice")
        self.data_manager.create_player("2", "Bob")
        question = Question("Q", "A", "C", 100)
        daily_question_id = self.data_manager.log_daily_question(question)
        self.data_manager.adjust_player_score("1", 100)
        self.data_manager.adjust_player_score("2", 50)
        self.data_manager.log_player_guess("1", "Alice", daily_question_id, "A", True)
        self.data_manager.log_player_guess("2", "Bob", daily_question_id, "B", False)

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

    def test_get_player_scores_includes_powerup_only_player(self):
        """A player with score who only used a power-up (no guesses) appears on the leaderboard."""
        self.db.execute_update(
            "INSERT INTO players (id, name, score) VALUES ('stealer', 'Stealer', 50)"
        )
        self.db.execute_update(
            "INSERT INTO daily_questions (id, question_id, sent_at) VALUES (1, 1, date('now'))"
        )
        # No guess row — only a powerup_usage row
        self.db.execute_update(
            "INSERT INTO powerup_usage (user_id, powerup_type, question_id, used_at) "
            "VALUES ('stealer', 'steal', 1, datetime('now'))"
        )

        scores = self.data_manager.get_player_scores()
        player_ids = [s["id"] for s in scores]
        self.assertIn("stealer", player_ids)

    def test_get_player_scores_excludes_powerup_only_player_beyond_28_days(self):
        """A player whose only activity is a powerup older than 28 days is excluded."""
        self.db.execute_update(
            "INSERT INTO players (id, name, score) VALUES ('old_stealer', 'OldStealer', 50)"
        )
        self.db.execute_update(
            "INSERT INTO daily_questions (id, question_id, sent_at) VALUES (1, 1, date('now'))"
        )
        self.db.execute_update(
            "INSERT INTO powerup_usage (user_id, powerup_type, question_id, used_at) "
            "VALUES ('old_stealer', 'steal', 1, datetime('now', '-30 days'))"
        )

        scores = self.data_manager.get_player_scores()
        player_ids = [s["id"] for s in scores]
        self.assertNotIn("old_stealer", player_ids)

    def test_get_player_streaks(self):
        """Return active persisted streaks ordered from longest to shortest."""
        self.data_manager.create_player("1", "Alice")
        self.data_manager.set_streak("1", 5)
        self.data_manager.create_player("2", "Bob")
        self.data_manager.set_streak("2", 3)
        self.data_manager.create_player("3", "Charlie")

        streaks = self.data_manager.get_player_streaks()
        self.assertEqual(len(streaks), 2)
        self.assertEqual(streaks[0]["answer_streak"], 5)
        self.assertEqual(streaks[1]["answer_streak"], 3)

    def test_get_question_by_id_not_found(self):
        """Return None when the canonical question ID is absent."""
        result = self.data_manager.get_question_by_id(999)
        self.assertIsNone(result)

    def test_get_question_by_id_found(self):
        """Read a question persisted through the real schema."""
        self.data_manager.log_daily_question(
            Question("Test Q", "Test A", "Test Cat", 100, "test", "Test Hint")
        )
        question_id = self.db.execute_query("SELECT id FROM questions")[0]["id"]

        result = self.data_manager.get_question_by_id(question_id)
        self.assertIsNotNone(result)
        self.assertEqual(result.question, "Test Q")
        self.assertEqual(result.answer, "Test A")

    def test_get_todays_daily_question_question_not_found(self):
        """Return None for a daily-question row with a missing question record."""
        self.db.execute_update(
            "INSERT INTO daily_questions (question_id, sent_at) VALUES (?, ?)",
            (999, date.today()),
        )
        result = self.data_manager.get_todays_daily_question()
        self.assertIsNone(result)

    def test_assign_role_to_player_existing_role(self):
        """Reusing a persisted role does not create duplicates."""
        self.data_manager.create_player("player1", "Player")
        self.data_manager.assign_role_to_player("player1", "Existing Role")
        self.data_manager.assign_role_to_player("player1", "Existing Role")
        role_count = self.db.execute_query(
            "SELECT COUNT(*) AS count FROM roles WHERE name = ?", ("Existing Role",)
        )[0]["count"]
        assignment_count = self.db.execute_query(
            "SELECT COUNT(*) AS count FROM player_roles WHERE player_id = ?",
            ("player1",),
        )[0]["count"]
        self.assertEqual(role_count, 1)
        self.assertEqual(assignment_count, 1)

    def test_get_most_recent_daily_question(self):
        """Retrieve a persisted historical daily question and its date."""
        yesterday = date.today() - timedelta(days=1)
        question = Question("Test Q", "Test A", "Test Cat", 100)
        expected_daily_question_id = self.data_manager.log_daily_question(question)
        self.db.execute_update(
            "UPDATE daily_questions SET sent_at = ? WHERE id = ?",
            (yesterday, expected_daily_question_id),
        )

        result = self.data_manager.get_most_recent_daily_question()

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 3)  # question, id, date
        question, daily_question_id, sent_date = result
        self.assertEqual(question.question, "Test Q")
        self.assertEqual(daily_question_id, expected_daily_question_id)
        self.assertEqual(sent_date, yesterday)

    def test_get_most_recent_daily_question_no_questions(self):
        """Return None when there are no daily questions."""
        result = self.data_manager.get_most_recent_daily_question()
        self.assertIsNone(result)

    def test_get_most_recent_daily_question_question_not_found(self):
        """Return None when the latest daily row references no question."""
        self.db.execute_update(
            "INSERT INTO daily_questions (question_id, sent_at) VALUES (?, ?)",
            (999, date.today()),
        )
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

    def test_get_hint_sent_timestamp_returns_none_without_hint(self):
        self.assertIsNone(self.data_manager.get_hint_sent_timestamp(1))


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
        # Create a question and daily question; powerups are keyed to daily_questions.id
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)

        # Create players
        self.data_manager.create_player("p1", "Player1")
        self.data_manager.create_player("p2", "Player2")

        # Log powerup usages against the daily_question id (not questions.id)
        self.data_manager.log_powerup_usage("p1", "shield", question_id=dq_id)
        self.data_manager.log_powerup_usage(
            "p2", "attack", target_user_id="p1", question_id=dq_id
        )

        # Retrieve usage for question
        usages = self.data_manager.get_powerup_usages_for_question(dq_id)
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

    def test_get_correct_solver_count(self):
        """Counts unique correct solvers, not total correct guesses."""
        # Create question
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)

        # Create players
        self.data_manager.create_player("p1", "Player1")
        self.data_manager.create_player("p2", "Player2")
        self.data_manager.create_player("p3", "Player3")

        # Initially 0
        count = self.data_manager.get_correct_solver_count(dq_id)
        self.assertEqual(count, 0)

        # Add guesses
        self.data_manager.log_player_guess("p1", "Player1", dq_id, "A", True)
        self.data_manager.log_player_guess("p1", "Player1", dq_id, "a", True)
        self.data_manager.log_player_guess("p2", "Player2", dq_id, "B", False)
        self.data_manager.log_player_guess("p3", "Player3", dq_id, "A", True)

        # Check count
        count = self.data_manager.get_correct_solver_count(dq_id)
        self.assertEqual(count, 2)

    def test_get_previous_daily_question_id(self):
        """Test retrieving the previous daily question ID using date-based lookup."""
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        # Create question on a past date
        dq_yesterday = self.data_manager.log_daily_question(q)
        yesterday = self.data_manager.get_today() - timedelta(days=1)
        self.data_manager._db.execute_update(
            "UPDATE daily_questions SET sent_at = ? WHERE id = ?",
            (yesterday.isoformat(), dq_yesterday),
        )
        # Create question for today
        dq_today = self.data_manager.log_daily_question(q, force_new=True)

        # First-ever question has no previous
        self.assertIsNone(
            self.data_manager.get_previous_daily_question_id(dq_yesterday)
        )
        # Today's question finds yesterday's
        self.assertEqual(
            self.data_manager.get_previous_daily_question_id(dq_today), dq_yesterday
        )

    def test_get_previous_daily_question_id_ignores_same_day_skip(self):
        """Same-day skip replacement should not be treated as yesterday's question."""
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        # Two questions on the same calendar day (original + skip replacement)
        dq_original = self.data_manager.log_daily_question(q)
        dq_replacement = self.data_manager.log_daily_question(q, force_new=True)

        # No previous calendar-day question exists for either
        self.assertIsNone(
            self.data_manager.get_previous_daily_question_id(dq_replacement)
        )

    def test_get_grace_period_players(self):
        """get_grace_period_players returns players who missed today but answered yesterday."""
        self.data_manager.create_player(
            "p1", "Player1"
        )  # answered yesterday, missing today
        self.data_manager.create_player("p2", "Player2")  # answered both days
        self.data_manager.create_player("p3", "Player3")  # missed both days

        self.data_manager.set_streak("p1", 5)
        self.data_manager.set_streak("p2", 3)
        self.data_manager.set_streak("p3", 7)

        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        # Yesterday: p1 and p2 answer correctly
        dq1 = self.data_manager.log_daily_question(q)
        yesterday = self.data_manager.get_today() - timedelta(days=1)
        self.data_manager._db.execute_update(
            "UPDATE daily_questions SET sent_at = ? WHERE id = ?",
            (yesterday.isoformat(), dq1),
        )
        self.data_manager.log_player_guess("p1", "Player1", dq1, "A", True)
        self.data_manager.log_player_guess("p2", "Player2", dq1, "A", True)

        # Today: only p2 answers
        dq2 = self.data_manager.log_daily_question(q, force_new=True)
        self.data_manager.log_player_guess("p2", "Player2", dq2, "A", True)

        grace = self.data_manager.get_grace_period_players(dq2)
        self.assertIn("p1", grace)  # missed today, answered yesterday → grace
        self.assertNotIn("p2", grace)  # answered today → not grace
        self.assertNotIn("p3", grace)  # missed both → no grace

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

    def test_clear_stale_rest_multipliers(self):
        """Stale multipliers (no rest today) are cleared; today's rest multiplier is preserved."""
        from data.readers.question import Question

        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)

        self.data_manager.create_player("p1", "Player1")  # stale multiplier
        self.data_manager.create_player("p2", "Player2")  # rested today
        self.data_manager.create_player("p3", "Player3")  # no multiplier

        # p1 has a leftover multiplier from a prior day (no powerup_usage row for this question)
        self.data_manager.increment_pending_multiplier("p1", 0.2)
        # p2 rested today
        self.data_manager.increment_pending_multiplier("p2", 0.2)
        self.data_manager.log_powerup_usage("p2", "rest", None, dq_id)

        self.data_manager.clear_stale_rest_multipliers(dq_id)

        self.assertEqual(self.data_manager.get_pending_multiplier("p1"), 0.0)
        self.assertGreater(self.data_manager.get_pending_multiplier("p2"), 0.0)
        self.assertEqual(self.data_manager.get_pending_multiplier("p3"), 0.0)


class TestGetDailyQuestionById(unittest.TestCase):
    """Integration tests for DataManager.get_daily_question_by_id."""

    def setUp(self):
        self.db = Database(":memory:")
        self.data_manager = DataManager(self.db)
        self.data_manager.initialize_database()

    def tearDown(self):
        self.db.close()

    def test_returns_question_and_id_for_existing_daily_question(self):
        q = Question("What is 2+2?", "4", "Math", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)
        self.assertIsNotNone(dq_id)

        result = self.data_manager.get_daily_question_by_id(dq_id)
        self.assertIsNotNone(result)
        question, question_id = result
        self.assertEqual(question.answer, "4")
        self.assertIsInstance(question_id, int)

    def test_returns_none_for_nonexistent_daily_question(self):
        result = self.data_manager.get_daily_question_by_id(99999)
        self.assertIsNone(result)


class TestGetSnapshotSeasonId(unittest.TestCase):
    """Integration tests for DataManager.get_snapshot_season_id."""

    def setUp(self):
        self.db = Database(":memory:")
        self.data_manager = DataManager(self.db)
        self.data_manager.initialize_database()

    def tearDown(self):
        self.db.close()

    def test_returns_none_when_no_snapshot(self):
        result = self.data_manager.get_snapshot_season_id(99999)
        self.assertIsNone(result)

    def test_returns_none_when_no_active_season(self):
        # No season created → snapshot season_id should be NULL
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        self.data_manager.create_player("p1", "Player1")
        dq_id = self.data_manager.log_daily_question(q)

        result = self.data_manager.get_snapshot_season_id(dq_id)
        self.assertIsNone(result)

    def test_returns_season_id_when_season_active(self):
        season_id = self.data_manager.create_season(
            "Test Season", "2024-01-01", "2024-01-31"
        )
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        self.data_manager.create_player("p1", "Player1")
        dq_id = self.data_manager.log_daily_question(q)

        result = self.data_manager.get_snapshot_season_id(dq_id)
        self.assertEqual(result, season_id)


class TestPendingPowerupDataManager(unittest.TestCase):
    """Integration tests for overnight preload DataManager methods."""

    def setUp(self):
        self.db = Database(":memory:")
        self.data_manager = DataManager(self.db)
        self.data_manager.initialize_database()
        self.data_manager.create_player("attacker", "Attacker")
        self.data_manager.create_player("target", "Target")

    def tearDown(self):
        self.db.close()

    def _insert_preload(self, user_id, powerup_type, target_user_id, question_id=None):
        self.data_manager.log_powerup_usage(
            user_id, powerup_type, target_user_id, question_id
        )

    def test_game_events_share_sequence_with_hydrated_preloads(self):
        question = Question("Q?", "A", "Cat", 100, "test", "Hint")
        daily_question_id = self.data_manager.log_daily_question(question)
        self._insert_preload("attacker", "jinx_preload", "target")
        self.data_manager.apply_pending_powerups(daily_question_id)
        self.data_manager.log_player_guess(
            "target", "Target", daily_question_id, "wrong", False
        )
        self.data_manager.log_powerup_usage("target", "rest", None, daily_question_id)

        powerups = self.data_manager.get_powerup_usages_for_question(daily_question_id)
        guesses = self.data_manager.get_guesses_for_daily_question(daily_question_id)
        self.assertEqual([row["event_sequence"] for row in powerups], [1, 3])
        self.assertEqual(guesses[0]["event_sequence"], 2)

    def test_legacy_events_remain_unsequenced_before_new_events(self):
        question = Question("Q?", "A", "Cat", 100, "test", "Hint")
        daily_question_id = self.data_manager.log_daily_question(question)
        self.db.execute_update(
            "INSERT INTO guesses (daily_question_id, player_id, guess_text, is_correct) "
            "VALUES (?, ?, ?, ?)",
            (daily_question_id, "target", "old", False),
        )
        self.data_manager.log_player_guess(
            "target", "Target", daily_question_id, "new", False
        )

        guesses = self.data_manager.get_guesses_for_daily_question(daily_question_id)
        self.assertEqual([row["event_sequence"] for row in guesses], [None, 1])

    def test_get_pending_powerup_returns_row(self):
        """get_pending_powerup returns a row when a NULL-qid preload exists."""
        self._insert_preload("attacker", "jinx_preload", "target")
        result = self.data_manager.get_pending_powerup("attacker")
        self.assertIsNotNone(result)
        self.assertEqual(result["user_id"], "attacker")
        self.assertEqual(result["powerup_type"], "jinx_preload")

    def test_get_pending_powerup_returns_none_when_empty(self):
        """get_pending_powerup returns None when no pending preloads exist."""
        result = self.data_manager.get_pending_powerup("attacker")
        self.assertIsNone(result)

    def test_get_pending_powerup_ignores_applied_rows(self):
        """get_pending_powerup ignores rows that already have a question_id assigned."""
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)
        self._insert_preload("attacker", "jinx_preload", "target", dq_id)
        result = self.data_manager.get_pending_powerup("attacker")
        self.assertIsNone(result)

    def test_get_pending_powerup_for_target_returns_row(self):
        """get_pending_powerup_for_target finds a matching pending row."""
        self._insert_preload("attacker", "steal_preload", "target")
        result = self.data_manager.get_pending_powerup_for_target(
            "target", "steal_preload"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["target_user_id"], "target")
        self.assertEqual(result["user_id"], "attacker")

    def test_get_pending_powerup_for_target_returns_none_when_empty(self):
        result = self.data_manager.get_pending_powerup_for_target(
            "target", "jinx_preload"
        )
        self.assertIsNone(result)

    def test_get_pending_powerup_for_target_filters_by_type(self):
        """get_pending_powerup_for_target does not match a different powerup type."""
        self._insert_preload("attacker", "steal_preload", "target")
        result = self.data_manager.get_pending_powerup_for_target(
            "target", "jinx_preload"
        )
        self.assertIsNone(result)

    def test_apply_pending_powerups_updates_row(self):
        """apply_pending_powerups sets question_id and returns the updated row."""
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)
        self._insert_preload("attacker", "jinx_preload", "target")

        rows = self.data_manager.apply_pending_powerups(dq_id)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["powerup_type"], "jinx_preload")
        updated = self.db.execute_query(
            "SELECT question_id FROM powerup_usage WHERE user_id = ?", ("attacker",)
        )
        self.assertEqual(updated[0]["question_id"], dq_id)

    def test_apply_pending_powerups_multiple_rows(self):
        """apply_pending_powerups processes all pending rows in one call."""
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)
        self._insert_preload("attacker", "jinx_preload", "target")
        self._insert_preload("target", "steal_preload", "attacker")

        rows = self.data_manager.apply_pending_powerups(dq_id)

        self.assertEqual(len(rows), 2)
        remaining = self.db.execute_query(
            "SELECT * FROM powerup_usage WHERE question_id IS NULL"
        )
        self.assertEqual(len(remaining), 0)

    def test_apply_pending_powerups_empty_returns_empty(self):
        """apply_pending_powerups returns [] when no pending rows exist."""
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)
        rows = self.data_manager.apply_pending_powerups(dq_id)
        self.assertEqual(rows, [])

    def test_apply_pending_powerups_skips_non_preload_types(self):
        """apply_pending_powerups only touches jinx_preload/steal_preload rows."""
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)
        self._insert_preload("attacker", "jinx", "target")  # live type, no qid
        self._insert_preload("target", "jinx_preload", "attacker")  # preload type

        rows = self.data_manager.apply_pending_powerups(dq_id)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["powerup_type"], "jinx_preload")
        # The bare 'jinx' row should still have NULL question_id
        untouched = self.db.execute_query(
            "SELECT question_id FROM powerup_usage WHERE user_id = ? AND powerup_type = 'jinx'",
            ("attacker",),
        )
        self.assertIsNone(untouched[0]["question_id"])

    def test_get_powerup_usages_for_question_after_apply(self):
        """After apply_pending_powerups, get_powerup_usages_for_question returns the rows."""
        q = Question("Q?", "A", "Cat", 100, "test", "Hint")
        dq_id = self.data_manager.log_daily_question(q)
        self._insert_preload("attacker", "steal_preload", "target")
        self.data_manager.apply_pending_powerups(dq_id)

        usages = self.data_manager.get_powerup_usages_for_question(dq_id)
        self.assertEqual(len(usages), 1)
        self.assertEqual(usages[0]["powerup_type"], "steal_preload")
        self.assertEqual(usages[0]["user_id"], "attacker")
        self.assertEqual(usages[0]["target_user_id"], "target")


class TestRollbackQuestionDay(unittest.TestCase):
    """Integration tests for DataManager.rollback_question_day using a real :memory: DB."""

    def setUp(self):
        self.db = Database(":memory:")
        self.dm = DataManager(self.db)
        self.dm.initialize_database()

        # Create two players.
        self.dm.create_player("alice", "Alice")
        self.dm.create_player("bob", "Bob")

        # Give them some baseline stats.
        self.dm.adjust_player_score("alice", 200)
        self.dm.set_streak("alice", 7)
        self.dm.adjust_player_score("bob", 100)
        self.dm.set_streak("bob", 3)

        # Log a daily question (triggers create_daily_snapshot automatically).
        q = Question("What?", "42", "Math", 10, "test", "Hint")
        self.dq_id = self.dm.log_daily_question(q)
        self.assertIsNotNone(self.dq_id)

    def tearDown(self):
        self.db.close()

    def _simulate_daytime_activity(self):
        """Mutate player state to simulate answer scoring during the question."""
        self.dm.adjust_player_score("alice", 50)  # alice earns 50 pts
        self.dm.increment_streak("alice")
        self.dm.adjust_player_score("bob", 30)
        self.dm.increment_streak("bob")

    def test_rollback_restores_player_score_and_streak(self):
        self._simulate_daytime_activity()

        # Sanity-check mutations happened.
        self.assertEqual(self.dm.get_player("alice").score, 250)
        self.assertEqual(self.dm.get_player("alice").answer_streak, 8)

        self.dm.rollback_question_day(self.dq_id)

        alice = self.dm.get_player("alice")
        self.assertEqual(alice.score, 200)
        self.assertEqual(alice.answer_streak, 7)

        bob = self.dm.get_player("bob")
        self.assertEqual(bob.score, 100)
        self.assertEqual(bob.answer_streak, 3)

    def test_rollback_re_nulls_hydrated_preloads(self):
        # Log an overnight preload, then hydrate it (simulates morning flow).
        self.dm.log_powerup_usage("alice", "jinx_preload", "bob", None)
        pending = self.dm.apply_pending_powerups(self.dq_id)
        self.assertEqual(len(pending), 1)

        # Confirm the row now has a non-NULL question_id.
        rows = self.db.execute_query(
            "SELECT question_id, event_sequence FROM powerup_usage WHERE powerup_type = 'jinx_preload'"
        )
        self.assertEqual(rows[0]["question_id"], self.dq_id)
        self.assertEqual(rows[0]["event_sequence"], 1)

        # Roll back — should re-NULL the preload so it can be re-hydrated.
        self.dm.rollback_question_day(self.dq_id)

        rows = self.db.execute_query(
            "SELECT question_id, event_sequence FROM powerup_usage WHERE powerup_type = 'jinx_preload'"
        )
        self.assertIsNone(rows[0]["question_id"])
        self.assertIsNone(rows[0]["event_sequence"])

    def test_rollback_does_not_re_null_non_preload_powerups(self):
        # Normal daytime powerup (e.g. steal with a real question_id) should NOT
        # be re-nulled by rollback.
        self.dm.log_powerup_usage("alice", "jinx", "bob", self.dq_id)

        self.dm.rollback_question_day(self.dq_id)

        rows = self.db.execute_query(
            "SELECT question_id FROM powerup_usage WHERE powerup_type = 'jinx'"
        )
        # question_id should still point to the original question, not NULL.
        self.assertEqual(rows[0]["question_id"], self.dq_id)

    def test_rollback_with_season_restores_season_scores(self):
        # Create a season and give players season points.
        season_id = self.dm.create_season("April 2026", "2026-04-01", "2026-04-30")
        self.dm.initialize_player_season_score("alice", season_id)
        self.dm.initialize_player_season_score("bob", season_id)
        self.dm.increment_season_stat("alice", season_id, "points", 50)
        self.dm.increment_season_stat("alice", season_id, "correct_answers", 1)
        self.dm.increment_season_stat("alice", season_id, "questions_answered", 1)
        self.dm.increment_season_stat("bob", season_id, "points", 30)

        # Take a fresh snapshot AFTER season is active (re-log a new question).
        q2 = Question("Q2?", "B", "Cat", 10, "test", "H2")
        dq2_id = self.dm.log_daily_question(q2, force_new=True)

        # Simulate scoring on that question.
        self.dm.increment_season_stat("alice", season_id, "points", 20)
        self.dm.increment_season_stat("alice", season_id, "correct_answers", 1)
        self.dm.increment_season_stat("alice", season_id, "questions_answered", 1)

        # Roll back — season points and questions_answered should return to
        # what was snapshotted.
        self.dm.rollback_question_day(dq2_id)

        ss = self.dm.get_player_season_score("alice", season_id)
        self.assertEqual(ss.points, 50)
        self.assertEqual(ss.correct_answers, 1)
        self.assertEqual(ss.questions_answered, 1)

    def test_rollback_no_snapshot_is_graceful(self):
        # Calling rollback for a question_id with no snapshot should not raise.
        try:
            self.dm.rollback_question_day(9999)
        except Exception:
            self.fail("rollback_question_day raised unexpectedly with missing snapshot")

    def test_snapshot_captures_pending_rest_multiplier(self):
        # Give alice a pending rest multiplier before the snapshot is taken.
        self.dm.increment_pending_multiplier("alice", 1.2)

        q2 = Question("Q2?", "B", "Cat", 10, "test", "H2")
        dq2_id = self.dm.log_daily_question(q2, force_new=True)

        # Consume the multiplier (simulate rest_wakeup clearing it).
        self.dm.clear_pending_multiplier("alice")
        self.assertEqual(self.dm.get_pending_multiplier("alice"), 0.0)

        # Rollback should restore the 1.2 multiplier.
        self.dm.rollback_question_day(dq2_id)
        self.assertAlmostEqual(self.dm.get_pending_multiplier("alice"), 1.2)

    def test_rollback_clears_rest_multiplier_set_during_question(self):
        # Player rests during the active question (multiplier set to 1.2).
        self.dm.increment_pending_multiplier("alice", 1.2)

        # Snapshot was taken BEFORE rest, so pending_rest_multiplier was 0.
        # That's already snapshotted in setUp (snapshot taken with 0.0).
        self.dm.rollback_question_day(self.dq_id)

        # Snapshot had 0.0, so the multiplier should be cleared.
        self.assertAlmostEqual(self.dm.get_pending_multiplier("alice"), 0.0)


class TestPowerUpManagerRollback(unittest.TestCase):
    """Integration tests for PowerUpManager.rollback_to_snapshot on a real DB."""

    def setUp(self):
        from src.core.player_manager import PlayerManager
        from src.core.powerup import PowerUpManager
        from tests.src.core._powerup_helpers import make_config

        self.db = Database(":memory:")
        self.data_manager = DataManager(self.db)
        self.player_manager = PlayerManager(self.data_manager)
        self.data_manager.create_player("player1", "Player1")
        self.data_manager.adjust_player_score("player1", 200)
        self.data_manager.set_streak("player1", 7)
        # Logging the question takes the player snapshot
        self.dq_id = self.data_manager.log_daily_question(
            Question("What?", "42", "Math", 10)
        )
        # ConfigReader is an external boundary
        self.powerup_manager = PowerUpManager(
            self.player_manager, self.data_manager, make_config()
        )

    def tearDown(self):
        self.db.close()

    def test_rollback_restores_persisted_player_state(self):
        self.data_manager.adjust_player_score("player1", 50)
        self.data_manager.increment_streak("player1")

        self.powerup_manager.rollback_to_snapshot(self.dq_id)

        player = self.data_manager.get_player("player1")
        self.assertEqual((player.score, player.answer_streak), (200, 7))

    def test_rollback_clears_in_memory_daily_state(self):
        from src.core.state import DailyPlayerState

        self.powerup_manager.daily_state["player1"] = DailyPlayerState()
        self.powerup_manager.daily_state["player2"] = DailyPlayerState()

        self.powerup_manager.rollback_to_snapshot(self.dq_id)

        self.assertEqual(self.powerup_manager.daily_state, {})


class TestGameRunnerRollbackOnSkip(unittest.TestCase):
    """Tests that _setup_new_question triggers rollback when force_new=True."""

    def setUp(self):
        # ConfigReader is an external boundary
        self.config_patcher = patch("src.core.game_runner.ConfigReader")
        MockConfig = self.config_patcher.start()
        self.addCleanup(self.config_patcher.stop)

        cfg = MockConfig.return_value
        defaults = {
            "JBOT_RIDDLE_HISTORY_DAYS": "30",
            "JBOT_QUESTION_RETRIES": "10",
            "JBOT_EMOJI_FASTEST": "🥇",
            "JBOT_EMOJI_FASTEST_CSV": "🥇,🥈,🥉",
            "JBOT_BONUS_FASTEST_CSV": "10,5,1",
            "JBOT_BONUS_TRY_CSV": "20,10,5",
            "JBOT_BONUS_BEFORE_HINT": "10",
            "JBOT_BONUS_STREAK_PER_DAY": "5",
            "JBOT_BONUS_STREAK_CAP": "25",
            "JBOT_EMOJI_FIRST_TRY": "🎯",
            "JBOT_EMOJI_BEFORE_HINT": "🧠",
            "JBOT_EMOJI_STREAK": "🔥",
            "JBOT_EMOJI_STREAK_BROKEN": "💔",
            "JBOT_EMOJI_JINXED": "🥶",
            "JBOT_EMOJI_SILENCED": "🤐",
            "JBOT_EMOJI_STOLEN_FROM": "💸",
            "JBOT_EMOJI_STEALING": "💰",
            "JBOT_EMOJI_REST": "😴",
            "JBOT_EMOJI_REST_WAKEUP": "⏰",
        }
        cfg.get.side_effect = lambda k, d=None: defaults.get(k, d)
        cfg.get_bool.side_effect = lambda k, d=False: False
        cfg.is_seasons_enabled.return_value = False

        self.db = Database(":memory:")
        self.addCleanup(self.db.close)
        self.dm = DataManager(self.db)
        # The question selector fronts the dataset / Gemini boundary
        self.mock_qs = MagicMock()
        self.mock_qs.get_hint_from_gemini.return_value = None
        from src.core.game_runner import GameRunner

        self.gr = GameRunner(self.mock_qs, self.dm)

        self.dm.create_player("alice", "Alice")
        self.dm.adjust_player_score("alice", 200)
        self.dm.set_streak("alice", 7)

    def _wire_new_question(self, text="Q?"):
        q = Question(text, "A", "C", 10, "h", "s")
        self.mock_qs.get_random_question.return_value = q
        return q

    def _alice(self):
        player = self.dm.get_player("alice")
        return player.score, player.answer_streak

    def _start_question_and_earn_points(self):
        """Start the day's question (snapshot at 200/7), then alice earns 50/+1."""
        self._wire_new_question("First?")
        self.assertTrue(self.gr._setup_new_question())
        self.dm.adjust_player_score("alice", 50)
        self.dm.increment_streak("alice")
        self.assertEqual(self._alice(), (250, 8))

    def test_skip_rolls_back_player_state_to_old_question_snapshot(self):
        self._start_question_and_earn_points()
        old_question_id = self.gr.daily_question_id
        self._wire_new_question("Replacement?")

        self.assertTrue(self.gr._setup_new_question(force_new=True))

        self.assertEqual(self._alice(), (200, 7))
        self.assertNotEqual(self.gr.daily_question_id, old_question_id)
        self.assertEqual(self.gr.daily_q.question, "Replacement?")

    def test_fresh_day_does_not_roll_back(self):
        self._start_question_and_earn_points()
        self.gr.daily_question_id = None  # No active question (fresh day).
        self._wire_new_question("Second?")

        self.assertTrue(self.gr._setup_new_question(force_new=False))

        self.assertEqual(self._alice(), (250, 8))

    def test_force_new_without_existing_question_skips_rollback(self):
        """force_new=True but daily_question_id is None — rollback is a no-op."""
        self._start_question_and_earn_points()
        self.gr.daily_question_id = None
        self._wire_new_question("Replacement?")

        self.assertTrue(self.gr._setup_new_question(force_new=True))

        self.assertEqual(self._alice(), (250, 8))


if __name__ == "__main__":
    unittest.main()
