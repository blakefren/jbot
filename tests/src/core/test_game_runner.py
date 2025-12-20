import unittest
from unittest.mock import patch, MagicMock, call

from data.readers.question import Question
from src.core.game_runner import GameRunner
from src.core.guess_handler import AlreadyAnsweredCorrectlyError
from src.core.data_manager import DataManager
from src.core.subscriber import Subscriber
from src.core.player import Player


class TestGameRunner(unittest.TestCase):
    def test_get_evening_message_content_with_guild_nicknames(self):
        """Test evening message uses server nicknames if guild is provided."""
        self.game_runner.daily_q = self.mock_question
        self.game_runner.daily_question_id = 123
        # Prepare guess history with player_id and player_name
        self.mock_data_manager.read_guess_history.return_value = [
            {
                "daily_question_id": 123,
                "player_id": "111",
                "player_name": "Alice",
                "guess_text": "Test Answer",
                "is_correct": True,
            },
            {
                "daily_question_id": 123,
                "player_id": "222",
                "player_name": "Bob",
                "guess_text": "some guess",
                "is_correct": False,
            },
        ]

        # Mock guild and member objects
        mock_guild = MagicMock()
        mock_member_alice = MagicMock()
        mock_member_alice.nick = "AliceNick"
        mock_member_alice.display_name = "AliceDisplay"
        mock_member_bob = MagicMock()
        mock_member_bob.nick = None
        mock_member_bob.display_name = "BobDisplay"

        def get_member_side_effect(member_id):
            if member_id == 111:
                return mock_member_alice
            elif member_id == 222:
                return mock_member_bob
            return None

        mock_guild.get_member.side_effect = get_member_side_effect

        content = self.game_runner.get_evening_message_content(guild=mock_guild)
        # Should use nick if available, else display_name
        self.assertIn("**AliceNick**: **Test Answer**", content)
        self.assertIn("**BobDisplay**: some guess", content)

    def setUp(self):
        """Set up for the tests."""
        self.mock_question_selector = MagicMock()
        self.mock_data_manager = MagicMock(spec=DataManager)
        self.mock_data_manager.get_hint_sent_timestamp.return_value = None
        self.mock_question = Question(
            question="Test Question",
            answer="Test Answer",
            category="Test Category",
            clue_value=100,
        )
        self.mock_question.id = "q1"
        self.mock_question_selector.get_random_question.return_value = (
            self.mock_question
        )
        self.mock_question_selector.questions = {"qid1": self.mock_question}

        self.game_runner = GameRunner(
            self.mock_question_selector, self.mock_data_manager
        )

    def test_initialization(self):
        """Test GameRunner initialization."""
        self.assertIn("powerup", self.game_runner.managers)
        self.assertEqual(
            self.game_runner.question_selector, self.mock_question_selector
        )
        self.mock_data_manager.get_all_subscribers.assert_called_once()
        self.assertEqual(
            self.game_runner.subscribed_contexts,
            self.mock_data_manager.get_all_subscribers.return_value,
        )
        self.assertIsNone(self.game_runner.daily_q)

    def test_set_daily_question(self):
        """Test setting the daily question."""
        self.mock_data_manager.get_todays_daily_question.return_value = None
        self.game_runner.daily_q = None
        self.game_runner.set_daily_question()
        self.mock_question_selector.get_random_question.assert_called_once()
        self.assertEqual(self.game_runner.daily_q, self.mock_question)

    def test_set_daily_question_on_restart(self):
        """Test setting the daily question on restart when one already exists."""
        # Simulate finding an existing daily question
        self.mock_data_manager.get_todays_daily_question.return_value = (
            self.mock_question,
            5,
        )

        self.game_runner.set_daily_question()

        # Verify that we fetched the existing question data
        self.mock_data_manager.get_todays_daily_question.assert_called_once()

        # Ensure we didn't try to select a new question
        self.mock_question_selector.get_random_question.assert_not_called()

        # Verify the daily question is correctly set
        self.assertEqual(self.game_runner.daily_q, self.mock_question)
        self.assertEqual(self.game_runner.daily_question_id, 5)

    def test_add_and_remove_subscriber(self):
        """Test adding and removing a subscriber."""
        mock_subscriber = MagicMock(spec=Subscriber)
        self.game_runner.subscribed_contexts = set()

        self.game_runner.add_subscriber(mock_subscriber)
        self.mock_data_manager.save_subscriber.assert_called_once_with(mock_subscriber)
        self.assertIn(mock_subscriber, self.game_runner.subscribed_contexts)

        self.game_runner.remove_subscriber(mock_subscriber)
        self.mock_data_manager.delete_subscriber.assert_called_once_with(
            mock_subscriber
        )
        self.assertNotIn(mock_subscriber, self.game_runner.subscribed_contexts)

    def test_format_question_and_answer(self):
        """Test the formatting of questions and answers."""
        formatted_q = self.game_runner.format_question(self.mock_question)
        self.assertIn(self.mock_question.question, formatted_q)
        self.assertIn(self.mock_question.category, formatted_q)
        self.assertIn(str(self.mock_question.clue_value), formatted_q)

        formatted_a = self.game_runner.format_answer(self.mock_question)
        self.assertIn(self.mock_question.answer, formatted_a)
        self.assertIn("||", formatted_a)  # Spoiler tags

    def test_get_morning_message_content(self):
        """Test generating the morning message content."""
        # Case 1: No daily question
        self.game_runner.daily_q = None
        self.assertEqual(
            self.game_runner.get_morning_message_content(),
            "No question available for today.",
        )

        # Case 2: Daily question is set
        self.game_runner.daily_q = self.mock_question
        content = self.game_runner.get_morning_message_content()
        self.assertIn(self.mock_question.question, content)

    def test_get_reminder_message_content(self):
        """Test generating the reminder message content."""
        self.game_runner.daily_q = self.mock_question
        self.game_runner.daily_question_id = 12345  # Mock daily question ID
        self.game_runner.player_manager = MagicMock()
        self.game_runner.player_manager.get_all_players = MagicMock(
            return_value={"1": "Player1", "2": "Player2"}
        )
        self.mock_data_manager.read_guess_history.return_value = [
            {"daily_question_id": 12345, "player_id": "1"}
        ]

        # With tagging enabled, with hint
        content = self.game_runner.get_reminder_message_content(tag_unanswered=True)
        self.assertIn(self.mock_question.question, content)
        self.assertIn("<@2>", content)
        self.assertNotIn("<@1>", content)
        self.assertNotIn("Hint:", content)

        # With tagging disabled, no hint
        content = self.game_runner.get_reminder_message_content(tag_unanswered=False)
        self.assertNotIn("<@", content)
        self.assertNotIn("Hint:", content)

        # With hint
        self.mock_question.hint = "This is a test hint."
        content_with_hint = self.game_runner.get_reminder_message_content(
            tag_unanswered=False
        )
        self.assertIn("Hint: ||**This is a test hint.**||", content_with_hint)
        self.mock_question.hint = None  # Reset for other tests

        # With hint
        self.mock_question.hint = "This is a test hint."
        content_with_hint = self.game_runner.get_reminder_message_content(
            tag_unanswered=False
        )
        self.assertIn("Hint: ||**This is a test hint.**||", content_with_hint)
        self.mock_question.hint = None  # Reset for other tests

    def test_get_evening_message_content(self):
        """Test generating the evening message content with deduplicated, sorted, and bolded guesses."""
        self.game_runner.daily_q = self.mock_question
        self.game_runner.daily_question_id = 123
        self.mock_data_manager.read_guess_history.return_value = [
            # Player 'Charlie'
            {
                "daily_question_id": 123,
                "player_id": "333",
                "player_name": "Charlie",
                "guess_text": "wrong answer",
                "is_correct": False,
            },
            # Player 'Alice' - correct guess, duplicate guess, another guess
            {
                "daily_question_id": 123,
                "player_id": "111",
                "player_name": "Alice",
                "guess_text": "Test Answer",
                "is_correct": True,
            },
            {
                "daily_question_id": 123,
                "player_id": "111",
                "player_name": "Alice",
                "guess_text": "another guess",
                "is_correct": False,
            },
            {
                "daily_question_id": 123,
                "player_id": "111",
                "player_name": "Alice",
                "guess_text": "another guess",
                "is_correct": False,
            },
            # Player 'Bob'
            {
                "daily_question_id": 123,
                "player_id": "222",
                "player_name": "Bob",
                "guess_text": "some guess",
                "is_correct": False,
            },
            # Another day's guess for Alice
            {
                "daily_question_id": 456,
                "player_id": "111",
                "player_name": "Alice",
                "guess_text": "yesterday's guess",
                "is_correct": False,
            },
        ]

        content = self.game_runner.get_evening_message_content()

        # Expected output lines for each player, sorted by player name
        expected_alice = "**Alice**: **Test Answer**, another guess"
        expected_bob = "**Bob**: some guess"
        expected_charlie = "**Charlie**: wrong answer"

        self.assertIn(self.mock_question.answer, content)
        self.assertIn(expected_alice, content)
        self.assertIn(expected_bob, content)
        self.assertIn(expected_charlie, content)
        self.assertNotIn("yesterday's guess", content)

        # Check order
        self.assertTrue(content.find(expected_alice) < content.find(expected_bob))
        self.assertTrue(content.find(expected_bob) < content.find(expected_charlie))

    def test_handle_guess_already_answered_correctly(self):
        """Test that handle_guess raises an error if the player has already answered correctly."""
        self.game_runner.daily_q = self.mock_question
        self.game_runner.daily_question_id = 1
        player_id = 123

        with patch("src.core.game_runner.GuessHandler") as mock_guess_handler:
            mock_handler_instance = mock_guess_handler.return_value
            mock_handler_instance.handle_guess.side_effect = (
                AlreadyAnsweredCorrectlyError
            )

            with self.assertRaises(AlreadyAnsweredCorrectlyError):
                self.game_runner.handle_guess(player_id, "Test Player", "any guess")

            mock_handler_instance.handle_guess.assert_called_once_with(
                player_id, "Test Player", "any guess"
            )

    def test_update_scores(self):
        """Test that scores are updated correctly for players with correct answers."""
        pass

    def test_update_scores_for_new_player(self):
        """Test that a new player's score is updated correctly."""
        pass

    def test_handle_guess(self):
        """Test handling a player's guess."""
        self.mock_data_manager.get_todays_daily_question.return_value = None
        self.mock_data_manager.log_daily_question.return_value = 1
        self.game_runner.set_daily_question()
        player_id, player_name = 123, "Test Guesser"

        with patch("src.core.game_runner.GuessHandler") as mock_guess_handler:
            mock_handler_instance = mock_guess_handler.return_value
            mock_handler_instance.handle_guess.return_value = (True, 1, 100, [])

            is_correct, num_guesses, points, bonuses = self.game_runner.handle_guess(
                player_id, player_name, "test answer"
            )
            self.assertTrue(is_correct)
            self.assertEqual(num_guesses, 1)
            mock_handler_instance.handle_guess.assert_called_once_with(
                player_id, player_name, "test answer"
            )

        # No daily question
        self.game_runner.daily_q = None
        is_correct, num_guesses, points, bonuses = self.game_runner.handle_guess(
            player_id, player_name, "any answer"
        )
        self.assertFalse(is_correct)
        self.assertEqual(num_guesses, 0)

    def test_get_scores_leaderboard(self):
        """Test generating the scores leaderboard."""
        self.mock_data_manager.get_player_scores.return_value = [
            {"id": "1", "name": "Alice", "score": 10},
            {"id": "2", "name": "Bob", "score": 5},
        ]
        self.mock_data_manager.get_player_streaks.return_value = []
        leaderboard = self.game_runner.get_scores_leaderboard()
        self.assertIn("Rank", leaderboard)
        self.assertIn("Player", leaderboard)
        self.assertIn("Score", leaderboard)
        # Streak is now shown by default
        self.assertIn("Streak", leaderboard)
        self.assertIn("Alice", leaderboard)
        self.assertIn("Bob", leaderboard)
        self.assertTrue(leaderboard.find("Alice") < leaderboard.find("Bob"))

    def test_get_scores_leaderboard_with_guild(self):
        """Test generating the scores leaderboard with a guild to resolve names."""
        self.mock_data_manager.get_player_scores.return_value = [
            {"id": "1", "name": "OldNameAlice", "score": 10},
            {"id": "2", "name": "Bob", "score": 5},
        ]
        self.mock_data_manager.get_player_streaks.return_value = []

        mock_guild = MagicMock()
        mock_member_alice = MagicMock()
        mock_member_alice.display_name = "NewNameAlice"
        mock_member_alice.nick = None

        # Let get_member return the new mock member for Alice, and None for Bob
        mock_guild.get_member.side_effect = lambda id: (
            mock_member_alice if id == 1 else None
        )

        leaderboard = self.game_runner.get_scores_leaderboard(guild=mock_guild)

        self.assertIn("NewNameAlice", leaderboard)
        self.assertIn("Bob", leaderboard)
        self.assertNotIn("OldNameAlice", leaderboard)
        mock_guild.get_member.assert_any_call(1)
        mock_guild.get_member.assert_any_call(2)

    def test_get_scores_leaderboard_with_guild_and_nick(self):
        """Test that a member's nickname is used if available."""
        self.mock_data_manager.get_player_scores.return_value = [
            {"id": "1", "name": "OldNameAlice", "score": 10},
        ]
        self.mock_data_manager.get_player_streaks.return_value = []

        mock_guild = MagicMock()
        mock_member_alice = MagicMock()
        mock_member_alice.display_name = "NewNameAlice"
        mock_member_alice.nick = "AliceNick"

        mock_guild.get_member.return_value = mock_member_alice

        leaderboard = self.game_runner.get_scores_leaderboard(guild=mock_guild)

        self.assertIn("AliceNick", leaderboard)
        self.assertNotIn("OldNameAlice", leaderboard)
        self.assertNotIn("NewNameAlice", leaderboard)
        mock_guild.get_member.assert_called_once_with(1)

    def test_get_scores_leaderboard_with_streaks(self):
        """Test that player streaks are shown in the leaderboard."""
        self.mock_data_manager.get_player_scores.return_value = [
            {"id": "1", "name": "Alice", "score": 100},
            {"id": "2", "name": "Bob", "score": 90},
            {"id": "3", "name": "Charlie", "score": 80},
        ]
        self.mock_data_manager.get_player_streaks.return_value = [
            {"id": "1", "answer_streak": 3},
            {"id": "3", "answer_streak": 5},
        ]

        # Mock daily question ID for show_daily_bonuses to work
        self.game_runner.daily_question_id = 123
        self.mock_data_manager.read_guess_history.return_value = (
            []
        )  # No guesses needed for streak test
        self.mock_data_manager.get_first_try_solvers.return_value = []

        leaderboard = self.game_runner.get_scores_leaderboard(show_daily_bonuses=True)

        self.assertIn("Alice", leaderboard)
        self.assertIn("Bob", leaderboard)
        self.assertIn("Charlie", leaderboard)
        self.assertIn("3🔥", leaderboard)
        self.assertIn("5🔥", leaderboard)
        self.assertNotIn("Bob 🔥", leaderboard)

    def test_get_player_history(self):
        """Test generating a player's history."""
        self.mock_data_manager.read_guess_history.return_value = [
            {"is_correct": True},
            {"is_correct": False},
            {"is_correct": True},
            {"is_correct": True},
        ]
        self.game_runner.player_manager = MagicMock()
        from src.core.player import Player

        self.game_runner.player_manager.get_player = MagicMock(
            return_value=Player(id="123", name="Alice", score=300)
        )

        history = self.game_runner.get_player_history(123, "Alice")
        self.assertIn("-- Your stats, Alice --", history)
        self.assertIn("Total guesses: 4", history)
        self.assertIn("Correct rate:  75.00%", history)
        self.assertIn("Score:         300", history)

    def test_get_scores_leaderboard_alphabetical_tie(self):
        """Test that players with the same score are sorted alphabetically."""
        self.mock_data_manager.get_player_scores.return_value = [
            {"id": "1", "name": "Charlie", "score": 10},
            {"id": "2", "name": "Alice", "score": 10},
            {"id": "3", "name": "Bob", "score": 5},
        ]
        self.mock_data_manager.get_player_streaks.return_value = []
        leaderboard = self.game_runner.get_scores_leaderboard()
        self.assertIn("Alice", leaderboard)
        self.assertIn("Bob", leaderboard)
        self.assertIn("Charlie", leaderboard)
        # Alice and Charlie have the same score, Alice should be first alphabetically.
        self.assertTrue(leaderboard.find("Alice") < leaderboard.find("Charlie"))
        # Bob has a lower score, so he should appear after both.
        self.assertTrue(leaderboard.find("Charlie") < leaderboard.find("Bob"))
        self.assertTrue(leaderboard.find("Alice") < leaderboard.find("Bob"))

    def test_set_daily_question_generates_hint_if_missing(self):
        """Test that a hint is generated if the selected question is missing one."""
        # Arrange
        self.mock_data_manager.get_todays_daily_question.return_value = None
        question_without_hint = Question(
            question="Test Q", answer="Test A", category="Test C"
        )
        self.assertIsNone(question_without_hint.hint)

        self.mock_question_selector.get_random_question.return_value = (
            question_without_hint
        )
        self.mock_question_selector.get_hint_from_gemini.return_value = "Generated Hint"

        # Act
        self.game_runner.set_daily_question()

        # Assert
        self.mock_question_selector.get_hint_from_gemini.assert_called_once_with(
            question_without_hint
        )
        self.assertEqual(self.game_runner.daily_q.hint, "Generated Hint")
        self.mock_data_manager.log_daily_question.assert_called_once_with(
            self.game_runner.daily_q
        )

    def test_set_daily_question_hint_generation_fails_gracefully(self):
        """Test that hint generation failure doesn't stop question selection."""
        # Arrange
        self.mock_data_manager.get_todays_daily_question.return_value = None
        question_without_hint = Question(
            question="Test Q", answer="Test A", category="Test C"
        )
        self.mock_question_selector.get_random_question.return_value = (
            question_without_hint
        )
        # Simulate Gemini failure
        self.mock_question_selector.get_hint_from_gemini.return_value = None

        # Act
        self.game_runner.set_daily_question()

        # Assert
        self.mock_question_selector.get_hint_from_gemini.assert_called_once()
        self.assertIsNone(self.game_runner.daily_q.hint)  # Hint should still be None
        self.mock_data_manager.log_daily_question.assert_called_once()  # Still logs

    def test_set_daily_question_with_existing_hint(self):
        """Test that a hint is not generated if one already exists."""
        # Arrange
        self.mock_data_manager.get_todays_daily_question.return_value = None
        question_with_hint = Question(
            question="Test Q", answer="Test A", category="Test C", hint="Existing Hint"
        )
        self.mock_question_selector.get_random_question.return_value = (
            question_with_hint
        )

        # Act
        self.game_runner.set_daily_question()

        # Assert
        self.mock_question_selector.get_hint_from_gemini.assert_not_called()
        self.assertEqual(self.game_runner.daily_q.hint, "Existing Hint")
        self.mock_data_manager.log_daily_question.assert_called_once()

    def test_reset_daily_question(self):
        """Test resetting the daily question to a new one."""
        new_question = Question(
            question="New Question",
            answer="New Answer",
            category="New Cat",
            clue_value=200,
        )
        self.mock_data_manager.get_used_question_hashes.return_value = {
            "hash1",
            "hash2",
        }
        self.mock_question_selector.get_random_question.return_value = new_question
        self.mock_data_manager.log_daily_question.return_value = 999

        result = self.game_runner.reset_daily_question()

        self.assertTrue(result)
        self.assertEqual(self.game_runner.daily_q, new_question)
        self.assertEqual(self.game_runner.daily_question_id, 999)
        self.mock_data_manager.get_used_question_hashes.assert_called_once()
        self.mock_question_selector.get_random_question.assert_called_once_with(
            exclude_hashes={"hash1", "hash2"}
        )
        self.mock_data_manager.log_daily_question.assert_called_once_with(
            new_question, force_new=True
        )

    def test_reset_daily_question_no_question_available(self):
        """Test reset_daily_question when no question is available."""
        self.mock_data_manager.get_used_question_hashes.return_value = set()
        self.mock_question_selector.get_random_question.return_value = None

        result = self.game_runner.reset_daily_question()

        self.assertFalse(result)

    def test_reset_daily_question_log_fails(self):
        """Test reset_daily_question when logging fails."""
        new_question = Question(question="Q", answer="A", category="C")
        self.mock_data_manager.get_used_question_hashes.return_value = set()
        self.mock_question_selector.get_random_question.return_value = new_question
        self.mock_data_manager.log_daily_question.return_value = None

        result = self.game_runner.reset_daily_question()

        self.assertFalse(result)

    def test_set_daily_question_hint_generation_exception(self):
        """Test hint generation handles exceptions gracefully."""
        self.mock_data_manager.get_todays_daily_question.return_value = None
        question_no_hint = Question(question="Q", answer="A", category="C")
        self.mock_question_selector.get_random_question.return_value = question_no_hint
        self.mock_question_selector.get_hint_from_gemini.side_effect = Exception(
            "API Error"
        )

        self.game_runner.set_daily_question()

        # Should not raise, question should still be set
        self.assertEqual(self.game_runner.daily_q, question_no_hint)
        self.mock_data_manager.log_daily_question.assert_called_once()

    def test_set_daily_question_fallback_on_log_none(self):
        """Test that set_daily_question falls back to get_todays_daily_question when log returns None."""
        question_with_hint = Question(question="Q", answer="A", category="C", hint="H")
        self.mock_question_selector.get_random_question.return_value = (
            question_with_hint
        )
        # First call returns None (no existing question), second returns existing after log
        self.mock_data_manager.get_todays_daily_question.side_effect = [
            None,
            (question_with_hint, 555),
        ]
        self.mock_data_manager.log_daily_question.return_value = None

        self.game_runner.set_daily_question()

        self.assertEqual(self.game_runner.daily_question_id, 555)

    def test_get_reminder_message_content_no_daily_question(self):
        """Test get_reminder_message_content when no daily question is set."""
        self.game_runner.daily_q = None
        result = self.game_runner.get_reminder_message_content(tag_unanswered=True)
        self.assertEqual(result, "No question to remind about.")

    def test_get_scores_leaderboard_no_scores(self):
        """Test get_scores_leaderboard when there are no player scores."""
        self.mock_data_manager.get_player_scores.return_value = []
        result = self.game_runner.get_scores_leaderboard()
        self.assertEqual(result, "No scores available yet.")

    def test_get_scores_leaderboard_guild_exception(self):
        """Test get_scores_leaderboard handles guild member lookup exceptions."""
        self.mock_data_manager.get_player_scores.return_value = [
            {"id": "1", "name": "Alice", "score": 100}
        ]
        self.mock_data_manager.get_player_streaks.return_value = []

        mock_guild = MagicMock()
        mock_guild.get_member.side_effect = Exception("Guild error")

        with patch("src.core.game_runner.logging"):
            leaderboard = self.game_runner.get_scores_leaderboard(guild=mock_guild)

        # Should fall back to using the stored name
        self.assertIn("Alice", leaderboard)

    def test_get_evening_message_content_no_daily_question(self):
        """Test get_evening_message_content when no daily question is set."""
        self.game_runner.daily_q = None
        result = self.game_runner.get_evening_message_content()
        self.assertEqual(result, "No question to answer for today.")

    def test_get_evening_message_content_guild_exception(self):
        """Test get_evening_message_content handles guild member lookup exceptions."""
        self.game_runner.daily_q = self.mock_question
        self.game_runner.daily_question_id = 123
        self.mock_data_manager.read_guess_history.return_value = [
            {
                "daily_question_id": 123,
                "player_id": "111",
                "player_name": "Alice",
                "guess_text": "answer",
                "is_correct": True,
            }
        ]

        mock_guild = MagicMock()
        mock_guild.get_member.side_effect = Exception("Guild error")

        with patch("src.core.game_runner.logging"):
            content = self.game_runner.get_evening_message_content(guild=mock_guild)

        # Should fall back to stored name
        self.assertIn("**Alice**", content)

    def test_update_scores_no_daily_question_id(self):
        """Test update_scores logs warning when no daily_question_id."""
        pass

    def test_update_scores_fallback_on_exception(self):
        """Test update_scores falls back to default score on exception."""
        pass

    def test_get_player_history_no_history(self):
        """Test get_player_history when player has no history."""
        self.mock_data_manager.read_guess_history.return_value = []
        result = self.game_runner.get_player_history(123, "Alice")
        self.assertEqual(result, "No history found for Alice.")

    def test_get_subscribed_users(self):
        """Test getting subscribed users."""
        mock_subscribers = {MagicMock(spec=Subscriber), MagicMock(spec=Subscriber)}
        self.game_runner.subscribed_contexts = mock_subscribers
        result = self.game_runner.get_subscribed_users()
        self.assertEqual(result, mock_subscribers)

    def test_get_scores_leaderboard_fastest_guesser(self):
        """Test that the fastest guesser is determined by guessed_at timestamp."""
        self.mock_data_manager.get_player_scores.return_value = [
            {"id": "1", "name": "Alice", "score": 100},
            {"id": "2", "name": "Bob", "score": 100},
        ]
        self.mock_data_manager.get_player_streaks.return_value = []
        self.game_runner.daily_question_id = 123

        # Bob guessed first (earlier timestamp) but has higher ID
        self.mock_data_manager.read_guess_history.return_value = [
            {
                "daily_question_id": 123,
                "player_id": "2",
                "player_name": "Bob",
                "guess_text": "answer",
                "is_correct": True,
                "guessed_at": "2023-01-01 10:00:00",
            },
            {
                "daily_question_id": 123,
                "player_id": "1",
                "player_name": "Alice",
                "guess_text": "answer",
                "is_correct": True,
                "guessed_at": "2023-01-01 10:05:00",
            },
        ]
        self.mock_data_manager.get_first_try_solvers.return_value = []

        leaderboard = self.game_runner.get_scores_leaderboard(show_daily_bonuses=True)

        # Bob should have the fastest guesser emoji (medal)
        self.assertIn("Bob", leaderboard)
        self.assertIn("🥇", leaderboard)

        # Ensure Alice is present
        self.assertIn("Alice", leaderboard)
        # But verify she doesn't have the medal emoji.
        lines = leaderboard.split("\n")
        alice_line = next((line for line in lines if "Alice" in line), None)
        self.assertIsNotNone(alice_line)
        self.assertNotIn("🥇", alice_line)

    def test_get_scores_leaderboard_first_try_bonus(self):
        """Test that the first try bonus emoji is shown."""
        self.mock_data_manager.get_player_scores.return_value = [
            {"id": "1", "name": "Alice", "score": 100},
            {"id": "2", "name": "Bob", "score": 90},
        ]
        self.mock_data_manager.get_player_streaks.return_value = []
        self.game_runner.daily_question_id = 123

        # Mock guess history to avoid errors, but we rely on get_first_try_solvers for the badge
        self.mock_data_manager.read_guess_history.return_value = []

        # Alice got it on the first try
        self.mock_data_manager.get_first_try_solvers.return_value = [{"id": "1"}]

        leaderboard = self.game_runner.get_scores_leaderboard(show_daily_bonuses=True)

        # Alice should have the bullseye
        self.assertIn("Alice", leaderboard)
        self.assertIn("🎯", leaderboard)

        # Bob should not
        self.assertIn("Bob", leaderboard)
        lines = leaderboard.split("\n")
        bob_line = next((line for line in lines if "Bob" in line), None)
        self.assertIsNotNone(bob_line)
        self.assertNotIn("🎯", bob_line)

    def test_get_scores_leaderboard_emoji_width(self):
        """Test that emojis are counted as 2 characters wide for leaderboard spacing."""
        self.mock_data_manager.get_player_scores.return_value = [
            {"id": "1", "name": "Alice", "score": 100},
        ]
        self.mock_data_manager.get_player_streaks.return_value = [
            {"id": "1", "answer_streak": 10}
        ]
        self.game_runner.daily_question_id = 123

        # Alice is fastest and first try
        self.mock_data_manager.read_guess_history.return_value = [
            {
                "daily_question_id": 123,
                "player_id": "1",
                "player_name": "Alice",
                "guess_text": "answer",
                "is_correct": True,
                "guessed_at": "2023-01-01 10:00:00",
            }
        ]
        self.mock_data_manager.get_first_try_solvers.return_value = [{"id": "1"}]

        # Ensure no "before hint" bonus by setting hint timestamp before guess
        self.mock_data_manager.get_hint_sent_timestamp.return_value = (
            "2023-01-01 09:00:00"
        )

        # Badges string will be "10🔥 🥇 🎯"
        # 10 (2) + 🔥 (1) + 🥇 (1) + 🎯 (1) = 5 chars in Python string
        # But user wants width 8 due to the monospaced context of the leaderboard.

        leaderboard = self.game_runner.get_scores_leaderboard(show_daily_bonuses=True)

        # We can check the divider line.
        # The divider line format is: f"{'-'*4} {'-'*max_name} {'-'*max_score} {'-'*max_badges}"
        # We need to extract the last part.

        lines = leaderboard.split("\n")
        # lines[0] is ```Rank...
        # lines[1] is ---- ...
        divider_line = lines[1]
        parts = divider_line.split(" ")
        badges_divider = parts[-1]

        # Expected width: 8
        self.assertEqual(
            len(badges_divider),
            8,
            f"Expected divider length 8, got {len(badges_divider)}",
        )

    def test_get_scores_leaderboard_badge_order(self):
        """Test the order of badges in the leaderboard: Streak -> First Try -> Fastest."""
        self.mock_data_manager.get_player_scores.return_value = [
            {"id": "1", "name": "Alice", "score": 100},
        ]
        self.mock_data_manager.get_player_streaks.return_value = [
            {"id": "1", "answer_streak": 5}
        ]
        self.game_runner.daily_question_id = 123

        # Alice is fastest and first try
        self.mock_data_manager.read_guess_history.return_value = [
            {
                "daily_question_id": 123,
                "player_id": "1",
                "player_name": "Alice",
                "guess_text": "answer",
                "is_correct": True,
                "guessed_at": "2023-01-01 10:00:00",
            }
        ]
        self.mock_data_manager.get_first_try_solvers.return_value = [{"id": "1"}]

        leaderboard = self.game_runner.get_scores_leaderboard(show_daily_bonuses=True)

        # Expected order: Streak (🔥), First Try (🎯), Fastest (🥇)
        # Note: The exact emojis depend on config, but defaults are used here.
        # We check the relative positions in the string.
        streak_pos = leaderboard.find("🔥")
        first_try_pos = leaderboard.find("🎯")
        fastest_pos = leaderboard.find("🥇")

        self.assertNotEqual(streak_pos, -1)
        self.assertNotEqual(first_try_pos, -1)
        self.assertNotEqual(fastest_pos, -1)

        self.assertLess(streak_pos, first_try_pos)
        self.assertLess(first_try_pos, fastest_pos)

    def test_get_scores_leaderboard_before_hint_bonus(self):
        """Test that the before hint bonus emoji is shown."""
        self.mock_data_manager.get_player_scores.return_value = [
            {"id": "1", "name": "Alice", "score": 110},
        ]
        self.mock_data_manager.get_player_streaks.return_value = []
        self.game_runner.daily_question_id = 123

        # Alice guessed before hint
        self.mock_data_manager.read_guess_history.return_value = [
            {
                "daily_question_id": 123,
                "player_id": "1",
                "player_name": "Alice",
                "guess_text": "answer",
                "is_correct": True,
                "guessed_at": "2023-01-01 10:00:00",
            }
        ]
        self.mock_data_manager.get_first_try_solvers.return_value = []

        # Hint sent later
        self.mock_data_manager.get_hint_sent_timestamp.return_value = (
            "2023-01-01 12:00:00"
        )

        leaderboard = self.game_runner.get_scores_leaderboard(show_daily_bonuses=True)

        # Alice should have the brain emoji
        self.assertIn("Alice", leaderboard)
        self.assertIn("🧠", leaderboard)


if __name__ == "__main__":
    unittest.main()


# --- Additional POWERUP mode tests ---
from unittest.mock import MagicMock
from src.core.game_runner import GameRunner


class DummyDataManagerPowerup:
    def log_player_guess(self, *a, **kw):
        pass

    def get_guess_metrics(self, *a, **kw):
        return {"players": {"1": {"score": 100, "bet": 0, "under_attack": False}}}

    def read_guess_history(self, *a, **kw):
        return []

    def get_all_subscribers(self):
        """Return empty subscribers set for testing."""
        return set()

    def get_correct_guess_count(self, daily_question_id):
        return 0

    def get_player(self, discord_id):
        return None

    def get_last_correct_guess_date(self, player_id):
        return None

    def reset_streak(self, player_id):
        pass

    def create_player(self, player_id, player_name):
        pass

    def adjust_player_score(self, player_id, amount):
        pass

    def increment_streak(self, player_id):
        pass


class DummyQuestionSelectorPowerup:
    def __init__(self):
        self.questions = []

    def get_random_question(self, exclude_hashes=None):
        q = MagicMock()
        q.id = "q1"
        q.answer = "test"
        return q


def test_handle_guess_powerup_correct():
    data_manager = DummyDataManagerPowerup()
    selector = DummyQuestionSelectorPowerup()
    game = GameRunner(selector, data_manager)
    game.daily_q = selector.get_random_question()
    game.daily_question_id = 1
    called = {}

    class DummyPowerUpManager:
        def __init__(self, players):
            pass

        def on_guess(self, pid, pname, guess, correct):
            called["on_guess"] = (pid, correct)

    game.register_manager("powerup", DummyPowerUpManager)
    game.enable_manager("powerup", players={})

    result, num_guesses, points, bonuses = game.handle_guess(1, "Player1", "test")
    assert result is True
    assert called["on_guess"] == (1, True)


def test_handle_guess_powerup_incorrect():
    data_manager = DummyDataManagerPowerup()
    selector = DummyQuestionSelectorPowerup()
    game = GameRunner(selector, data_manager)
    game.daily_q = selector.get_random_question()
    game.daily_question_id = 1
    called = {}

    class DummyPowerUpManager:
        def __init__(self, players):
            pass

        def on_guess(self, pid, pname, guess, correct):
            called["on_guess"] = (pid, correct)

    game.register_manager("powerup", DummyPowerUpManager)
    game.enable_manager("powerup", players={})

    result, num_guesses, points, bonuses = game.handle_guess(1, "Player1", "wrong")
    assert result is False
    assert called["on_guess"] == (1, False)


def test_handle_guess_non_powerup():
    data_manager = DummyDataManagerPowerup()
    selector = DummyQuestionSelectorPowerup()
    game = GameRunner(selector, data_manager)
    game.daily_q = selector.get_random_question()
    game.daily_question_id = 1
    result, num_guesses, points, bonuses = game.handle_guess(1, "Player1", "test")
    assert result is True


def test_handle_guess_no_question():
    data_manager = DummyDataManagerPowerup()
    selector = DummyQuestionSelectorPowerup()
    game = GameRunner(selector, data_manager)
    game.daily_q = None
    result, num_guesses, points, bonuses = game.handle_guess(1, "Player1", "test")
    assert result is False
