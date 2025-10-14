import unittest
from unittest.mock import patch, MagicMock, call

from data.readers.question import Question
from src.core.game_runner import GameRunner
from src.core.data_manager import DataManager
from src.core.subscriber import Subscriber


class TestGameRunner(unittest.TestCase):
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
        self.mock_question_selector.get_question_for_today.return_value = (
            self.mock_question
        )
        self.mock_question_selector.questions = {"qid1": self.mock_question}

        # Patch Subscriber class
        self.subscriber_patcher = patch("src.core.game_runner.Subscriber")
        self.MockSubscriber = self.subscriber_patcher.start()

        self.game_runner = GameRunner(self.mock_question_selector, self.mock_data_manager)

    def tearDown(self):
        """Tear down after tests."""
        self.subscriber_patcher.stop()

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
        self.game_runner.daily_q = None
        self.game_runner.set_daily_question()
        self.mock_question_selector.get_question_for_today.assert_called_once()
        self.assertEqual(self.game_runner.daily_q, self.mock_question)

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
        """Test generating the evening message content with grouped player guesses."""
        self.game_runner.daily_q = self.mock_question
        self.game_runner.daily_question_id = 123
        self.mock_data_manager.read_guess_history.return_value = [
            {
                "daily_question_id": 123,
                "player_name": "Player1",
                "guess_text": "guess1",
            },
            {
                "daily_question_id": 123,
                "player_name": "Player2",
                "guess_text": "guessA",
            },
            {
                "daily_question_id": 123,
                "player_name": "Player1",
                "guess_text": "guess2",
            },
            {
                "daily_question_id": 456,  # from another day
                "player_name": "Player1",
                "guess_text": "guess3",
            },
        ]

        content = self.game_runner.get_evening_message_content()
        self.assertIn(self.mock_question.answer, content)
        self.assertIn("Player1: guess1, guess2", content)
        self.assertIn("Player2: guessA", content)
        self.assertNotIn("guess3", content)

    def test_handle_guess(self):
        """Test handling a player's guess."""
        self.game_runner.set_daily_question()
        player_id, player_name = 123, "Test Guesser"

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
        self.assertIn("1. Alice: 10", leaderboard)
        self.assertIn("2. Bob: 5", leaderboard)
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
        
        self.assertIn("1. NewNameAlice: 10", leaderboard)
        self.assertIn("2. Bob: 5", leaderboard)
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
        
        self.assertIn("1. AliceNick: 10", leaderboard)
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
        self.game_runner.player_manager.get_player = MagicMock(return_value={'score': 300})

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
