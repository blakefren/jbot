import unittest
import os
import csv
from unittest.mock import patch, MagicMock, mock_open

from modes.game_runner import GameRunner, GameType
from bot.subscriber import Subscriber
from readers.question import Question
from database.logger import Logger
from cfg.players import read_players_into_dict


class TestGameRunner(unittest.TestCase):
    def setUp(self):
        """Set up for the tests."""
        self.mock_question_selector = MagicMock()
        self.mock_logger = MagicMock(spec=Logger)
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

        # Create a dummy subscribers file path
        self.test_subscribers_file = "test_subscribers.csv"

        # Patch SUBSCRIBERS_FILE before initializing GameRunner
        self.subscribers_patcher = patch(
            "modes.game_runner.SUBSCRIBERS_FILE", self.test_subscribers_file
        )
        self.subscribers_patcher.start()

        self.game_runner = GameRunner(self.mock_question_selector, self.mock_logger)

    def tearDown(self):
        """Tear down after tests."""
        if os.path.exists(self.test_subscribers_file):
            os.remove(self.test_subscribers_file)
        self.subscribers_patcher.stop()

    def test_initialization(self):
        """Test GameRunner initialization."""
        self.assertEqual(self.game_runner.mode, GameType.SIMPLE)
        self.assertEqual(
            self.game_runner.question_selector, self.mock_question_selector
        )
        self.assertEqual(self.game_runner.subscribed_contexts, set())
        self.assertIsNone(self.game_runner.daily_q)

    def test_set_daily_question(self):
        """Test setting the daily question."""
        self.game_runner.daily_q = None
        self.game_runner.set_daily_question()
        self.mock_question_selector.get_question_for_today.assert_called_once()
        self.assertEqual(self.game_runner.daily_q, self.mock_question)

    def test_load_subscribers(self):
        """Test loading subscribers from a CSV file."""
        # Create a dummy subscribers csv
        with open(self.test_subscribers_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "display_name", "is_channel"])
            writer.writerow(["123", "Test User", "False"])

        # Re-initialize to load the new file
        game_runner = GameRunner(self.mock_question_selector, self.mock_logger)
        self.assertEqual(len(game_runner.subscribed_contexts), 1)
        subscriber = list(game_runner.subscribed_contexts)[0]
        self.assertEqual(subscriber.id, 123)
        self.assertEqual(subscriber.display_name, "Test User")
        self.assertFalse(subscriber.is_channel)

    def test_add_and_remove_subscriber(self):
        """Test adding and removing a subscriber."""
        subscriber = Subscriber("456", "Another User", True)

        self.game_runner.add_subscriber(subscriber)
        self.assertIn(subscriber, self.game_runner.subscribed_contexts)

        # Verify it was saved
        with open(self.test_subscribers_file, "r") as f:
            content = f.read()
            self.assertIn("456,Another User,True", content)

        self.game_runner.remove_subscriber(subscriber)
        self.assertNotIn(subscriber, self.game_runner.subscribed_contexts)

        # Verify it was removed from file
        with open(self.test_subscribers_file, "r") as f:
            content = f.read()
            self.assertNotIn("456,Another User,True", content)

    def test_change_mode(self):
        """Test changing the game mode."""
        self.assertEqual(self.game_runner.mode, GameType.SIMPLE)
        self.game_runner.change_mode(GameType.POKER)
        self.assertEqual(self.game_runner.mode, GameType.POKER)

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

    @patch("modes.game_runner.read_players_into_dict")
    def test_get_reminder_message_content(self, mock_read_players):
        """Test generating the reminder message content."""
        self.game_runner.daily_q = self.mock_question
        mock_read_players.return_value = {"1": "Player1", "2": "Player2"}
        self.mock_logger.read_guess_history.return_value = [
            {"QuestionID": self.mock_question.id, "PlayerID": "1"}
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

    def test_get_evening_message_content(self):
        """Test generating the evening message content."""
        self.game_runner.daily_q = self.mock_question
        self.mock_logger.read_guess_history.return_value = [
            {
                "QuestionID": 110004699642252617987064134833407364497,
                "PlayerName": "Player1",
                "Guess": "A guess",
            }
        ]

        content = self.game_runner.get_evening_message_content()
        self.assertIn(self.mock_question.answer, content)
        self.assertIn("Player1: A guess", content)

    def test_handle_guess(self):
        """Test handling a player's guess."""
        self.game_runner.daily_q = self.mock_question
        player_id, player_name = 123, "Test Guesser"

        # Correct guess
        is_correct = self.game_runner.handle_guess(
            player_id, player_name, "test answer"
        )
        self.assertTrue(is_correct)
        self.mock_logger.log_player_guess.assert_called_with(
            player_id,
            player_name,
            110004699642252617987064134833407364497,
            "test answer",
            True,
        )

        # Incorrect guess
        is_correct = self.game_runner.handle_guess(
            player_id, player_name, "wrong answer"
        )
        self.assertFalse(is_correct)
        self.mock_logger.log_player_guess.assert_called_with(
            player_id,
            player_name,
            110004699642252617987064134833407364497,
            "wrong answer",
            False,
        )

        # No daily question
        self.game_runner.daily_q = None
        is_correct = self.game_runner.handle_guess(player_id, player_name, "any answer")
        self.assertFalse(is_correct)

    def test_get_scores_leaderboard(self):
        """Test generating the scores leaderboard."""
        self.mock_logger.get_guess_metrics.return_value = {
            "players": {
                "1": {"player_name": "Alice", "score": 10},
                "2": {"player_name": "Bob", "score": 5},
            }
        }
        leaderboard = self.game_runner.get_scores_leaderboard()
        self.assertIn("1. Alice: 10", leaderboard)
        self.assertIn("2. Bob: 5", leaderboard)
        self.assertTrue(leaderboard.find("Alice") < leaderboard.find("Bob"))

    def test_get_player_history(self):
        """Test generating a player's history."""
        self.mock_logger.get_guess_metrics.return_value = {
            "players": {
                "123": {
                    "guesses": 5,
                    "correct_rate": 0.8,
                    "score": 4,
                }
            },
            "global_correct_rate": 0.75,
            "total_guesses": 10,
            "unique_questions": 8,
            "global_score": 7,
        }
        history = self.game_runner.get_player_history(123, "Alice")
        self.assertIn("--Your stats, Alice--", history)
        self.assertIn("Total guesses: 5", history)
        self.assertIn("Correct rate:  0.80", history)
        self.assertIn("Score:         4", history)
        self.assertIn("Global score:     7", history)


if __name__ == "__main__":
    unittest.main()


# --- Additional POWERUP mode tests ---
import pytest
from unittest.mock import MagicMock
from modes.game_runner import GameRunner, GameType

class DummyLoggerPowerup:
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

def test_handle_guess_powerup_correct(monkeypatch):
    logger = DummyLoggerPowerup()
    selector = DummyQuestionSelectorPowerup()
    game = GameRunner(selector, logger, mode=GameType.POWERUP)
    game.daily_q = selector.get_question_for_today()
    called = {}
    class DummyPowerUpManager:
        def __init__(self, players):
            pass
        def resolve_bet(self, pid, correct):
            called["resolve_bet"] = (pid, correct)
    monkeypatch.setattr("modes.game_runner.PowerUpManager", DummyPowerUpManager)
    result = game.handle_guess(1, "Player1", "test")
    assert result is True
    assert called["resolve_bet"] == ("1", True)

def test_handle_guess_powerup_incorrect(monkeypatch):
    logger = DummyLoggerPowerup()
    selector = DummyQuestionSelectorPowerup()
    game = GameRunner(selector, logger, mode=GameType.POWERUP)
    game.daily_q = selector.get_question_for_today()
    called = {}
    class DummyPowerUpManager:
        def __init__(self, players):
            pass
        def resolve_bet(self, pid, correct):
            called["resolve_bet"] = (pid, correct)
    monkeypatch.setattr("modes.game_runner.PowerUpManager", DummyPowerUpManager)
    result = game.handle_guess(1, "Player1", "wrong")
    assert result is False
    assert called["resolve_bet"] == ("1", False)

def test_handle_guess_non_powerup():
    logger = DummyLoggerPowerup()
    selector = DummyQuestionSelectorPowerup()
    game = GameRunner(selector, logger, mode=GameType.SIMPLE)
    game.daily_q = selector.get_question_for_today()
    result = game.handle_guess(1, "Player1", "test")
    assert result is True

def test_handle_guess_no_question():
    logger = DummyLoggerPowerup()
    selector = DummyQuestionSelectorPowerup()
    game = GameRunner(selector, logger, mode=GameType.POWERUP)
    game.daily_q = None
    result = game.handle_guess(1, "Player1", "test")
    assert result is False
