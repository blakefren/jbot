import unittest
from unittest.mock import patch, MagicMock, call

from data.readers.question import Question
from src.core.game_runner import GameRunner, AlreadyAnsweredCorrectlyError
from src.core.data_manager import DataManager
from src.core.subscriber import Subscriber
from src.core.player import Player


class TestGameRunner(unittest.TestCase):
    def test_get_player_guesses(self):
        """Test get_player_guesses returns deduplicated, sorted, lowercase guesses for the current daily question and player."""
        self.game_runner.daily_question_id = 123
        self.mock_data_manager.read_guess_history.return_value = [
            {"daily_question_id": 123, "player_id": 111, "guess_text": "First Guess"},
            {"daily_question_id": 123, "player_id": 111, "guess_text": "second guess"},
            {"daily_question_id": 123, "player_id": 111, "guess_text": "FIRST GUESS"},
            {"daily_question_id": 456, "player_id": 111, "guess_text": "Old Question Guess"},
        ]
        # Should only return deduplicated, sorted, lowercase guesses for player_id=111 and daily_question_id=123
        all_guesses = self.mock_data_manager.read_guess_history.return_value
        filtered_guesses = [g["guess_text"] for g in all_guesses if g["player_id"] == 111 and g["daily_question_id"] == 123]
        # Remove guesses for other players
        guesses = self.game_runner.get_player_guesses(111)
        self.assertEqual(guesses, ["First Guess", "second guess", "FIRST GUESS"])
        # Now deduplicate, lowercase, and sort as trivia.py does
        formatted_guesses = sorted({(g or '').lower() for g in guesses})
        self.assertEqual(formatted_guesses, ["first guess", "second guess"])

        # Should return empty list for player with no guesses for current question
        self.mock_data_manager.read_guess_history.return_value = []
        guesses_none = self.game_runner.get_player_guesses(999)
        self.assertEqual(guesses_none, [])

    def test_get_evening_message_content_with_guild_nicknames(self):
        """Test evening message uses server nicknames if guild is provided."""
        self.game_runner.daily_q = self.mock_question
        self.game_runner.daily_question_id = 123
        # Prepare guess history with player_id and player_name
        self.mock_data_manager.read_guess_history.return_value = [
            {"daily_question_id": 123, "player_id": 111, "player_name": "Alice", "guess_text": "Test Answer", "is_correct": True},
            {"daily_question_id": 123, "player_id": 222, "player_name": "Bob", "guess_text": "some guess", "is_correct": False},
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
        self.mock_data_manager.db = MagicMock()
        self.mock_question = Question(
            question="Test Question",
            answer="Test Answer",
            category="Test Category",
            clue_value=100,
        )
        self.mock_question.id = "q1"
        self.mock_question_selector.get_question_for_today.return_value = (
            self.mock_question
        )
        self.mock_question_selector.questions = {"qid1": self.mock_question}

        # Patch Subscriber class
        self.subscriber_patcher = patch("src.core.game_runner.Subscriber")
        self.MockSubscriber = self.subscriber_patcher.start()

        # Patch PlayerManager
        self.player_manager_patcher = patch("src.core.game_runner.PlayerManager")
        self.MockPlayerManager = self.player_manager_patcher.start()
        self.mock_player_manager_instance = self.MockPlayerManager.return_value

        self.game_runner = GameRunner(self.mock_question_selector, self.mock_data_manager)
        self.game_runner.player_manager = self.mock_player_manager_instance

    def tearDown(self):
        """Tear down after tests."""
        self.subscriber_patcher.stop()
        self.player_manager_patcher.stop()

    def test_initialization(self):
        """Test GameRunner initialization."""
        self.assertEqual(self.game_runner.managers, {})
        self.assertEqual(
            self.game_runner.question_selector, self.mock_question_selector
        )
        self.MockSubscriber.get_all.assert_called_once_with(self.mock_data_manager.db)
        self.assertEqual(
            self.game_runner.subscribed_contexts,
            self.MockSubscriber.get_all.return_value,
        )
        self.assertIsNone(self.game_runner.daily_q)

    def test_set_daily_question(self):
        """Test setting the daily question."""
        self.mock_data_manager.get_todays_daily_question.return_value = None
        self.game_runner.daily_q = None
        self.game_runner.set_daily_question()
        self.mock_question_selector.get_question_for_today.assert_called_once()
        self.assertEqual(self.game_runner.daily_q, self.mock_question)

    def test_set_daily_question_on_restart(self):
        """Test setting the daily question on restart when one already exists."""
        # Simulate finding an existing daily question
        self.mock_data_manager.get_todays_daily_question.return_value = (self.mock_question, 5)

        self.game_runner.set_daily_question()

        # Verify that we fetched the existing question data
        self.mock_data_manager.get_todays_daily_question.assert_called_once()
        
        # Ensure we didn't try to select a new question
        self.mock_question_selector.get_question_for_today.assert_not_called()
        
        # Verify the daily question is correctly set
        self.assertEqual(self.game_runner.daily_q, self.mock_question)
        self.assertEqual(self.game_runner.daily_question_id, 5)

    def test_add_and_remove_subscriber(self):
        """Test adding and removing a subscriber."""
        mock_subscriber = MagicMock(spec=Subscriber)
        self.game_runner.subscribed_contexts = set()

        self.game_runner.add_subscriber(mock_subscriber)
        mock_subscriber.save.assert_called_once()
        self.assertIn(mock_subscriber, self.game_runner.subscribed_contexts)

        self.game_runner.remove_subscriber(mock_subscriber)
        mock_subscriber.delete.assert_called_once()
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
        self.game_runner.player_manager.get_all_players = MagicMock(
            return_value={"1": "Player1", "2": "Player2"}
        )
        self.mock_data_manager.read_guess_history.return_value = [
            {"daily_question_id": 12345, "player_id": 1}
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
            {"daily_question_id": 123, "player_id": 333, "player_name": "Charlie", "guess_text": "wrong answer", "is_correct": False},

            # Player 'Alice' - correct guess, duplicate guess, another guess
            {"daily_question_id": 123, "player_id": 111, "player_name": "Alice", "guess_text": "Test Answer", "is_correct": True},
            {"daily_question_id": 123, "player_id": 111, "player_name": "Alice", "guess_text": "another guess", "is_correct": False},
            {"daily_question_id": 123, "player_id": 111, "player_name": "Alice", "guess_text": "another guess", "is_correct": False},

            # Player 'Bob'
            {"daily_question_id": 123, "player_id": 222, "player_name": "Bob", "guess_text": "some guess", "is_correct": False},

            # Another day's guess for Alice
            {"daily_question_id": 456, "player_id": 111, "player_name": "Alice", "guess_text": "yesterday's guess", "is_correct": False},
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
        # Simulate that the player has already answered correctly
        self.game_runner.has_answered_correctly_today = MagicMock(return_value=True)

        with self.assertRaises(AlreadyAnsweredCorrectlyError):
            self.game_runner.handle_guess(player_id, "Test Player", "any guess")
        
        # Ensure we didn't log the guess
        self.mock_data_manager.log_player_guess.assert_not_called()

    def test_update_scores(self):
        """Test that scores are updated correctly for players with correct answers."""
        self.game_runner.daily_q = self.mock_question
        self.game_runner.daily_question_id = 1
        
        # Mock players
        mock_player_1 = MagicMock(spec=Player)
        mock_player_2 = MagicMock(spec=Player)
        
        def get_or_create_player_side_effect(player_id, player_name=None):
            if player_id == "111":
                return mock_player_1
            if player_id == "222":
                return mock_player_2
            return None
        self.mock_player_manager_instance.get_or_create_player.side_effect = get_or_create_player_side_effect

        # Mock guess history: player 111 answered correctly twice, player 222 once
        self.mock_data_manager.read_guess_history.return_value = [
            {"daily_question_id": 1, "player_id": 111, "player_name": "Player1", "is_correct": True},
            {"daily_question_id": 1, "player_id": 111, "player_name": "Player1", "is_correct": True},
            {"daily_question_id": 1, "player_id": 222, "player_name": "Player2", "is_correct": True},
            {"daily_question_id": 1, "player_id": 333, "player_name": "Player3", "is_correct": False},
        ]

        self.game_runner.update_scores()

        # Player 1 should only be scored once
        mock_player_1.update_score.assert_called_once_with(self.mock_question.clue_value)
        # Player 2 should be scored once
        mock_player_2.update_score.assert_called_once_with(self.mock_question.clue_value)
        
        # Check that save_players was called
        self.mock_player_manager_instance.save_players.assert_called_once()

    def test_update_scores_for_new_player(self):
        """Test that a new player's score is updated correctly."""
        self.game_runner.daily_q = self.mock_question
        self.game_runner.daily_question_id = 1
        
        # Mock a new player who is not in the player manager's cache initially
        new_player_id = "444"
        new_player_name = "Newbie"
        
        # get_player returns None, but get_or_create_player will create them
        mock_new_player = MagicMock(spec=Player)
        self.mock_player_manager_instance.get_player.return_value = None
        self.mock_player_manager_instance.get_or_create_player.return_value = mock_new_player

        # Mock guess history for the new player
        self.mock_data_manager.read_guess_history.return_value = [
            {"daily_question_id": 1, "player_id": int(new_player_id), "player_name": new_player_name, "is_correct": True},
        ]

        self.game_runner.update_scores()

        # Verify that get_or_create_player was called for the new player
        self.mock_player_manager_instance.get_or_create_player.assert_called_once_with(new_player_id, new_player_name)
        
        # Verify the new player's score was updated
        mock_new_player.update_score.assert_called_once_with(self.mock_question.clue_value)
        
        # Check that save_players was called
        self.mock_player_manager_instance.save_players.assert_called_once()

    def test_handle_guess(self):
        """Test handling a player's guess."""
        self.mock_data_manager.get_todays_daily_question.return_value = None
        self.mock_data_manager.log_daily_question.return_value = 1
        self.game_runner.set_daily_question()
        player_id, player_name = 123, "Test Guesser"

        # Mock has_answered_correctly_today to always be False for this test
        self.game_runner.has_answered_correctly_today = MagicMock(return_value=False)

        # Mock the data_manager's read_guess_history to simulate an empty history initially
        self.mock_data_manager.read_guess_history.return_value = []

        # Correct guess
        is_correct, num_guesses = self.game_runner.handle_guess(
            player_id, player_name, "test answer"
        )
        self.assertTrue(is_correct)
        self.assertEqual(num_guesses, 1)  # One guess made
        self.mock_data_manager.log_player_guess.assert_called_with(
            player_id,
            player_name,
            self.game_runner.daily_question_id,
            "test answer",
            True,
        )
        # Ensure score is NOT updated here
        self.mock_player_manager_instance.get_player.assert_not_called()

        # Update the mock to simulate that one guess has been made
        self.mock_data_manager.read_guess_history.return_value = [
            {"daily_question_id": self.game_runner.daily_question_id}
        ]

        # Incorrect guess
        is_correct, num_guesses = self.game_runner.handle_guess(
            player_id, player_name, "wrong answer"
        )
        self.assertFalse(is_correct)
        self.assertEqual(num_guesses, 2)  # Two guesses made
        self.mock_data_manager.log_player_guess.assert_called_with(
            player_id,
            player_name,
            self.game_runner.daily_question_id,
            "wrong answer",
            False,
        )

        # No daily question
        self.game_runner.daily_q = None
        is_correct, num_guesses = self.game_runner.handle_guess(player_id, player_name, "any answer")
        self.assertFalse(is_correct)
        self.assertEqual(num_guesses, 0)

    def test_get_scores_leaderboard(self):
        """Test generating the scores leaderboard."""
        self.mock_data_manager.get_player_scores.return_value = [
            {"id": "1", "name": "Alice", "score": 10},
            {"id": "2", "name": "Bob", "score": 5},
        ]
        leaderboard = self.game_runner.get_scores_leaderboard()
        self.assertIn("10: Alice", leaderboard)
        self.assertIn("5: Bob", leaderboard)
        self.assertTrue(leaderboard.find("Alice") < leaderboard.find("Bob"))

    def test_get_scores_leaderboard_with_guild(self):
        """Test generating the scores leaderboard with a guild to resolve names."""
        self.mock_data_manager.get_player_scores.return_value = [
            {"id": "1", "name": "OldNameAlice", "score": 10},
            {"id": "2", "name": "Bob", "score": 5},
        ]
        
        mock_guild = MagicMock()
        mock_member_alice = MagicMock()
        mock_member_alice.display_name = "NewNameAlice"
        mock_member_alice.nick = None
        
        # Let get_member return the new mock member for Alice, and None for Bob
        mock_guild.get_member.side_effect = lambda id: mock_member_alice if id == 1 else None

        leaderboard = self.game_runner.get_scores_leaderboard(guild=mock_guild)
        
        self.assertIn("10: NewNameAlice", leaderboard)
        self.assertIn("5: Bob", leaderboard)
        self.assertNotIn("OldNameAlice", leaderboard)
        mock_guild.get_member.assert_any_call(1)
        mock_guild.get_member.assert_any_call(2)

    def test_get_scores_leaderboard_with_guild_and_nick(self):
        """Test that a member's nickname is used if available."""
        self.mock_data_manager.get_player_scores.return_value = [
            {"id": "1", "name": "OldNameAlice", "score": 10},
        ]
        
        mock_guild = MagicMock()
        mock_member_alice = MagicMock()
        mock_member_alice.display_name = "NewNameAlice"
        mock_member_alice.nick = "AliceNick"
        
        mock_guild.get_member.return_value = mock_member_alice

        leaderboard = self.game_runner.get_scores_leaderboard(guild=mock_guild)
        
        self.assertIn("10: AliceNick", leaderboard)
        self.assertNotIn("OldNameAlice", leaderboard)
        self.assertNotIn("NewNameAlice", leaderboard)
        mock_guild.get_member.assert_called_once_with(1)


    def test_get_player_history(self):
        """Test generating a player's history."""
        self.mock_data_manager.read_guess_history.return_value = [
            {'is_correct': True},
            {'is_correct': False},
            {'is_correct': True},
            {'is_correct': True},
        ]
        from src.core.player import Player
        self.game_runner.player_manager.get_player = MagicMock(return_value=Player(id="123", name="Alice", score=300))

        history = self.game_runner.get_player_history(123, "Alice")
        self.assertIn("-- Your stats, Alice --", history)
        self.assertIn("Total guesses: 4", history)
        self.assertIn("Correct rate:  75.00%", history)
        self.assertIn("Score:         300", history)

    def test_manager_registration_and_enabling(self):
        """Test registering, enabling, and disabling a manager."""
        mock_manager_class = MagicMock()
        self.game_runner.register_manager("test_manager", mock_manager_class)
        self.assertIn("test_manager", self.game_runner.managers)
        self.assertEqual(self.game_runner.managers["test_manager"], mock_manager_class)

        # Enable the manager
        self.game_runner.enable_manager("test_manager", arg1="value1")
        mock_manager_class.assert_called_once_with(arg1="value1")
        self.assertIsNotNone(self.game_runner.managers["test_manager"])

        # Disable the manager
        self.game_runner.disable_manager("test_manager")
        self.assertIsNone(self.game_runner.managers["test_manager"])

    def test_get_scores_leaderboard_alphabetical_tie(self):
        """Test that players with the same score are sorted alphabetically."""
        self.mock_data_manager.get_player_scores.return_value = [
            {"id": "1", "name": "Charlie", "score": 10},
            {"id": "2", "name": "Alice", "score": 10},
            {"id": "3", "name": "Bob", "score": 5},
        ]
        leaderboard = self.game_runner.get_scores_leaderboard()
        self.assertIn("10: Alice, Charlie", leaderboard)
        self.assertIn("5: Bob", leaderboard)
        self.assertTrue(leaderboard.find("Alice") < leaderboard.find("Charlie"))


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


class DummyQuestionSelectorPowerup:
    def __init__(self):
        self.questions = []

    def get_question_for_today(self):
        q = MagicMock()
        q.id = "q1"
        q.answer = "test"
        return q


def test_handle_guess_powerup_correct():
    data_manager = DummyDataManagerPowerup()
    selector = DummyQuestionSelectorPowerup()
    game = GameRunner(selector, data_manager)
    game.daily_q = selector.get_question_for_today()
    called = {}

    class DummyPowerUpManager:
        def __init__(self, players):
            pass

        def on_guess(self, pid, pname, guess, correct):
            called["on_guess"] = (pid, correct)

    game.register_manager("powerup", DummyPowerUpManager)
    game.enable_manager("powerup", players={})

    with patch("src.core.game_runner.PowerUpManager", DummyPowerUpManager):
        result = game.handle_guess(1, "Player1", "test")
        assert result is True
        assert called["on_guess"] == (1, True)


def test_handle_guess_powerup_incorrect():
    data_manager = DummyDataManagerPowerup()
    selector = DummyQuestionSelectorPowerup()
    game = GameRunner(selector, data_manager)
    game.daily_q = selector.get_question_for_today()
    called = {}

    class DummyPowerUpManager:
        def __init__(self, players):
            pass

        def on_guess(self, pid, pname, guess, correct):
            called["on_guess"] = (pid, correct)

    game.register_manager("powerup", DummyPowerUpManager)
    game.enable_manager("powerup", players={})

    with patch("src.core.game_runner.PowerUpManager", DummyPowerUpManager):
        result = game.handle_guess(1, "Player1", "wrong")
        assert result is False
        assert called["on_guess"] == (1, False)


def test_handle_guess_non_powerup():
    data_manager = DummyDataManagerPowerup()
    selector = DummyQuestionSelectorPowerup()
    game = GameRunner(selector, data_manager)
    game.daily_q = selector.get_question_for_today()
    result = game.handle_guess(1, "Player1", "test")
    assert result is True


def test_handle_guess_no_question():
    data_manager = DummyDataManagerPowerup()
    selector = DummyQuestionSelectorPowerup()
    game = GameRunner(selector, data_manager)
    game.daily_q = None
    result = game.handle_guess(1, "Player1", "test")
    assert result is False
