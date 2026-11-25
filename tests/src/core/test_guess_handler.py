import unittest
import sqlite3
from unittest.mock import patch
from src.core.events import GuessContext
from src.core.guess_handler import (
    GuessHandler,
    AlreadyAnsweredCorrectlyError,
    JinxedError,
)
from src.core.data_manager import DataManager
from src.core.player_manager import PlayerManager
from src.core.powerup import PowerUpManager
from src.core.season_manager import SeasonManager
from db.database import Database
from data.readers.question import Question
from tests.src.core._powerup_helpers import make_config, make_stack


class _RecordingManager:
    """Stand-in for a pluggable game manager (e.g. PowerUpManager).

    The GuessHandler `managers` mapping is a collaborator seam rather than a data
    boundary, so a tiny recording fake keeps the context-passing assertions
    independent of any particular manager while everything else stays real.
    """

    def __init__(self):
        self.contexts = []

    def can_answer(self, player_id, hint_sent=False):
        return True, ""

    def on_guess(self, ctx):
        self.contexts.append(ctx)
        return []


class TestGuessHandler(unittest.TestCase):
    PLAYERS = [
        ("1", "PlayerOne", 0, 0),
        ("2", "PlayerTwo", 0, 0),
        ("3", "PlayerThree", 0, 0),
        ("4", "PlayerFour", 0, 0),
        ("5", "PlayerFive", 0, 0),
        ("6", "PlayerSix", 0, 0),
        ("o1", "Other1", 0, 0),
        ("o2", "Other2", 0, 0),
        ("o3", "Other3", 0, 0),
    ]

    def setUp(self):
        self.daily_question = Question(
            "Test Question", "Test Answer", "Test Category", 100, "Test Hint"
        )
        self.stack = make_stack(self, self.PLAYERS, question=self.daily_question)
        self.data_manager = self.stack.data_manager
        self.player_manager = self.stack.player_manager
        self.daily_question_id = self.stack.question_id
        self.config = make_config()
        self.recorder = _RecordingManager()
        self.guess_handler = self._make_handler()

    def _make_handler(self, **overrides):
        kwargs = dict(
            daily_question=self.daily_question,
            daily_question_id=self.daily_question_id,
            managers={"recorder": self.recorder},
            config=self.config,
            question_db_id=self.stack.question_db_id,
        )
        kwargs.update(overrides)
        return GuessHandler(self.data_manager, self.player_manager, **kwargs)

    def _seed_solvers(self, count):
        """Make `count` other players answer today's question correctly first."""
        for index in range(1, count + 1):
            self.stack.mark_answered_today(f"o{index}")

    def _log_guess(self, player_id, guess, is_correct, daily_question_id=None):
        player = self.player_manager.get_player(player_id)
        self.data_manager.log_player_guess(
            player_id,
            player.name,
            daily_question_id or self.daily_question_id,
            guess,
            is_correct,
        )

    def test_handle_guess_correct(self):
        """Test handling a correct guess."""
        player_id = 1
        player_name = "PlayerOne"
        guess = "Test Answer"
        self._seed_solvers(1)  # Not first

        is_correct, num_guesses, points, bonuses = self.guess_handler.handle_guess(
            player_id, player_name, guess
        )

        self.assertTrue(is_correct)
        self.assertEqual(num_guesses, 1)
        history = self.data_manager.read_guess_history(
            user_id="1", daily_question_id=self.daily_question_id
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["guess_text"], guess.lower())
        self.assertTrue(history[0]["is_correct"])

        # Streak is incremented and the score persisted
        player = self.player_manager.get_player("1")
        self.assertEqual(player.answer_streak, 1)
        self.assertGreater(points, 0)
        self.assertEqual(player.score, points)

        # Managers receive a GuessContext describing the guess
        self.assertEqual(len(self.recorder.contexts), 1)
        ctx = self.recorder.contexts[0]
        self.assertIsInstance(ctx, GuessContext)
        self.assertEqual(ctx.player_id, player_id)
        self.assertEqual(ctx.player_name, player_name)
        self.assertEqual(ctx.guess, guess)
        self.assertTrue(ctx.is_correct)

    def test_handle_guess_incorrect(self):
        """Test handling an incorrect guess."""
        player_id = 2
        player_name = "PlayerTwo"
        guess = "Wrong Answer"

        is_correct, num_guesses, points, bonuses = self.guess_handler.handle_guess(
            player_id, player_name, guess
        )

        self.assertFalse(is_correct)
        self.assertEqual(num_guesses, 1)
        history = self.data_manager.read_guess_history(
            user_id="2", daily_question_id=self.daily_question_id
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["guess_text"], guess.lower())
        self.assertFalse(history[0]["is_correct"])

        # Verify streak logic: nothing is scored or incremented
        player = self.player_manager.get_player("2")
        self.assertEqual(player.answer_streak, 0)
        self.assertEqual(player.score, 0)

        self.assertEqual(len(self.recorder.contexts), 1)
        ctx = self.recorder.contexts[0]
        self.assertIsInstance(ctx, GuessContext)
        self.assertEqual(ctx.player_id, player_id)
        self.assertEqual(ctx.player_name, player_name)
        self.assertEqual(ctx.guess, guess)
        self.assertFalse(ctx.is_correct)

    def test_handle_guess_already_answered_correctly(self):
        """Test that an error is raised if a player has already answered correctly."""
        self._log_guess("3", "test answer", True)

        with self.assertRaises(AlreadyAnsweredCorrectlyError):
            self.guess_handler.handle_guess(3, "PlayerThree", "Another Answer")

        self.assertEqual(len(self.data_manager.read_guess_history(user_id="3")), 1)

    def test_get_player_guesses(self):
        """Test retrieving a player's guesses for the current question."""
        old_question_id = self.daily_question_id
        self._log_guess("4", "old_guess", False)  # Not for today's question
        self.daily_question_id = self.stack.new_question_day(
            Question("New Question", "New Answer", "Test Category", 100)
        )
        self._log_guess("4", "guess1", False)
        self._log_guess("4", "guess2", False)
        self.assertNotEqual(old_question_id, self.daily_question_id)

        guesses = self._make_handler().get_player_guesses(4)
        self.assertEqual(len(guesses), 2)
        self.assertIn("guess1", guesses)
        self.assertIn("guess2", guesses)

    def test_has_answered_correctly_today_true(self):
        """Test checking if a player has answered correctly today when they have."""
        self._log_guess("5", "test answer", True)

        self.assertTrue(self.guess_handler.has_answered_correctly_today(5))

    def test_has_answered_correctly_today_false(self):
        """Test checking if a player has answered correctly today when they have not."""
        self._log_guess("6", "wrong", False)

        self.assertFalse(self.guess_handler.has_answered_correctly_today(6))

    def test_has_answered_correctly_today_ignores_other_questions(self):
        """A correct answer to an earlier question does not count for today's."""
        self.stack.answer_on_earlier_day("6", days_ago=1)

        self.assertFalse(self.guess_handler.has_answered_correctly_today(6))

    def test_get_player_guesses_no_daily_question_id(self):
        """Test get_player_guesses returns empty list when no daily_question_id."""
        self._log_guess("4", "guess1", False)
        handler = self._make_handler(daily_question_id=None)
        result = handler.get_player_guesses(player_id=4)
        self.assertEqual(result, [])

    def test_has_answered_correctly_today_no_daily_question_id(self):
        """Test has_answered_correctly_today returns False when no daily_question_id."""
        self._log_guess("5", "test answer", True)
        handler = self._make_handler(daily_question_id=None)
        result = handler.has_answered_correctly_today(player_id=5)
        self.assertFalse(result)

    def test_handle_guess_no_daily_question(self):
        """Test handle_guess returns False when there's no daily question."""
        handler = self._make_handler(daily_question=None, daily_question_id=None)
        result, num_guesses, points, bonuses = handler.handle_guess(
            1, "PlayerOne", "guess"
        )
        self.assertFalse(result)
        self.assertEqual(num_guesses, 0)
        self.assertEqual(self.data_manager.read_guess_history(), [])

    def test_handle_guess_blocked_for_silenced_player(self):
        """A jinxed player cannot guess before the hint; the guess is not recorded."""
        powerups = PowerUpManager(self.player_manager, self.data_manager, self.config)
        powerups._get_daily_state("1").silenced = True
        handler = self._make_handler(managers={"powerup": powerups})

        with self.assertRaises(JinxedError):
            handler.handle_guess(1, "PlayerOne", "Test Answer")
        self.assertEqual(self.data_manager.read_guess_history(user_id="1"), [])

        self.stack.send_hint()
        is_correct, _, _, _ = handler.handle_guess(1, "PlayerOne", "Test Answer")
        self.assertTrue(is_correct)

    def test_handle_guess_streak_increment(self):
        """Test that streak is incremented upon correct guess."""
        player_id = 1
        player_name = "PlayerOne"
        guess = "Test Answer"

        # Player with an existing streak who last answered yesterday
        self.data_manager.update_lifetime_stats(
            "1", answer_streak=5, lifetime_best_streak=5
        )
        self.stack.answer_on_earlier_day("1", days_ago=1)

        # Hint already sent and three faster solvers: no hint or fastest bonus
        self.stack.send_hint()
        self._seed_solvers(3)

        is_correct, num_guesses, points, bonuses = self.guess_handler.handle_guess(
            player_id, player_name, guess
        )

        self.assertTrue(is_correct)
        player = self.player_manager.get_player("1")
        # Streak should be incremented
        self.assertEqual(player.answer_streak, 6)
        self.assertEqual(player.lifetime_best_streak, 6)
        # Bonus should be based on new streak (6)
        # 100 (base) + 20 (first try) + 25 (streak: min(6 * 5, 25)) = 145
        self.assertEqual(points, 145)
        self.assertEqual(player.score, 145)
        self.assertTrue(any("6-day streak!" in msg for msg in bonuses))

    def test_handle_guess_streak_no_double_increment(self):
        """Test that streak is NOT incremented twice on the same day (e.g. after a skip)."""
        player_id = 1
        player_name = "PlayerOne"
        guess = "Test Answer"

        # Player with existing streak that was already incremented today by an
        # earlier (skipped) question
        self.data_manager.update_lifetime_stats(
            "1", answer_streak=6, lifetime_best_streak=6
        )
        self.stack.answer_on_earlier_day("1", days_ago=0)

        # Hint already sent and three faster solvers: no hint or fastest bonus
        self.stack.send_hint()
        self._seed_solvers(3)

        is_correct, num_guesses, points, bonuses = self.guess_handler.handle_guess(
            player_id, player_name, guess
        )

        self.assertTrue(is_correct)
        # Streak should NOT be incremented again
        player = self.player_manager.get_player("1")
        self.assertEqual(player.answer_streak, 6)
        # Bonus should still be awarded based on current streak (6)
        # 100 (base) + 20 (first try) + 25 (streak: min(6 * 5, 25)) = 145
        self.assertEqual(points, 145)
        self.assertEqual(player.score, 145)
        self.assertTrue(any("6-day streak!" in msg for msg in bonuses))

    def test_handle_guess_before_hint_bonus(self):
        """Test that bonus points are awarded if guess is before hint."""
        from datetime import time
        from zoneinfo import ZoneInfo

        handler = self._make_handler(reminder_time=time(12, 0, tzinfo=ZoneInfo("UTC")))
        # One faster solver and no hint sent yet - player should get before-hint bonus
        self._seed_solvers(1)

        is_correct, num_guesses, points, bonuses = handler.handle_guess(
            1, "PlayerOne", "Test Answer"
        )

        self.assertTrue(is_correct)
        # Base points (100) + First Try (20) + Before Hint Bonus (10) + 2nd Fastest (5) = 135
        self.assertEqual(points, 135)
        self.assertTrue(any("Pre-hint!" in msg for msg in bonuses))

    def _make_season_handler(self, seasons_enabled):
        config = make_config()
        config.is_seasons_enabled.return_value = seasons_enabled
        season_id = self.data_manager.create_season(
            "Test Season", "2000-01-01", "2999-12-31"
        )
        handler = self._make_handler(
            season_manager=SeasonManager(self.data_manager, config)
        )
        return handler, season_id

    def test_season_stats_updated_when_seasons_enabled(self):
        """Season stats are recorded when seasons flag is on and answer is correct."""
        handler, season_id = self._make_season_handler(True)

        is_correct, _, points, _ = handler.handle_guess(1, "Alice", "Test Answer")

        self.assertTrue(is_correct)
        season_score = self.data_manager.get_player_season_score("1", season_id)
        self.assertEqual(season_score.correct_answers, 1)
        self.assertEqual(season_score.first_answers, 1)
        self.assertEqual(season_score.questions_answered, 1)
        # Season points and streak are handled by update_score()/increment_streak()
        self.assertEqual(season_score.points, points)
        self.assertEqual(season_score.current_streak, 1)

    def test_season_stats_not_updated_when_seasons_disabled(self):
        """Season stat counters are NOT updated when the seasons flag is off."""
        handler, season_id = self._make_season_handler(False)

        is_correct, _, _, _ = handler.handle_guess(1, "Alice", "Test Answer")

        self.assertTrue(is_correct)
        season_score = self.data_manager.get_player_season_score("1", season_id)
        if season_score is not None:
            self.assertEqual(season_score.correct_answers, 0)
            self.assertEqual(season_score.first_answers, 0)
            self.assertEqual(season_score.questions_answered, 0)

    def test_lifetime_stats_always_updated_on_correct_answer(self):
        """Lifetime stat increments fire on a correct answer regardless of seasons flag."""
        # No season_manager
        is_correct, _, _, _ = self.guess_handler.handle_guess(1, "Alice", "Test Answer")

        self.assertTrue(is_correct)
        player = self.player_manager.get_player("1")
        self.assertEqual(player.lifetime_correct, 1)
        self.assertEqual(player.lifetime_questions, 1)
        self.assertEqual(player.lifetime_first_answers, 1)
        self.assertEqual(player.lifetime_best_streak, 1)

    def test_fastest_badge_counts_unique_players_not_total_guesses(self):
        """Award rank two after one player's wrong and correct guesses."""
        handler = self._make_handler(managers={})

        handler.handle_guess("1", "PlayerOne", "wrong answer")
        handler.handle_guess("1", "PlayerOne", "Test Answer")
        _, _, player_b_points, player_b_messages = handler.handle_guess(
            "2", "PlayerTwo", "Test Answer"
        )

        self.assertEqual(player_b_points, 135)
        self.assertTrue(any("2nd Fastest" in message for message in player_b_messages))
        self.assertEqual(len(self.data_manager.read_guess_history("1")), 2)


class TestGuessHandlerSQLiteWorkflow(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.data_manager = DataManager(self.db)
        self.player_manager = PlayerManager(self.data_manager)
        self.player_manager.get_or_create_player("1", "Player")
        question = Question("Question", "Answer", "Test", 100)
        self.daily_question_id = self.data_manager.log_daily_question(question)
        question_data = self.data_manager.get_todays_daily_question()
        self.question_db_id = question_data[2]
        self.handler = GuessHandler(
            self.data_manager,
            self.player_manager,
            question,
            self.daily_question_id,
            managers={},
            config=make_config(),
            question_db_id=self.question_db_id,
        )

    def tearDown(self):
        self.db.close()

    def test_correct_guess_persists_history_score_and_streak(self):
        is_correct, guess_count, points, _ = self.handler.handle_guess(
            "1", "Player", "Answer"
        )

        history = self.data_manager.read_guess_history("1")
        player = self.player_manager.get_player("1")
        self.assertTrue(is_correct)
        self.assertEqual(guess_count, 1)
        self.assertTrue(history[0]["is_correct"])
        self.assertGreater(points, 0)
        self.assertEqual(player.score, points)
        self.assertEqual(player.answer_streak, 1)

    def test_wrong_guess_persists_without_score_or_streak(self):
        is_correct, guess_count, points, _ = self.handler.handle_guess(
            "1", "Player", "Wrong"
        )

        history = self.data_manager.read_guess_history("1")
        player = self.player_manager.get_player("1")
        self.assertFalse(is_correct)
        self.assertEqual(guess_count, 1)
        self.assertFalse(history[0]["is_correct"])
        self.assertEqual(points, 0)
        self.assertEqual(player.score, 0)
        self.assertEqual(player.answer_streak, 0)

    def test_correct_guess_database_error_rolls_back_all_writes(self):
        def fail_guess_log(*args, **kwargs):
            self.db.execute_update("INSERT INTO missing_table VALUES (1)")

        with patch.object(
            self.data_manager, "log_player_guess", side_effect=fail_guess_log
        ):
            with self.assertRaises(sqlite3.OperationalError):
                self.handler.handle_guess("1", "Player", "Answer")

        player = self.player_manager.get_player("1")
        self.assertEqual(self.data_manager.read_guess_history("1"), [])
        self.assertEqual(player.score, 0)
        self.assertEqual(player.answer_streak, 0)
        self.assertEqual(player.lifetime_questions, 0)
        self.assertEqual(player.lifetime_correct, 0)

    def test_powerup_state_restores_when_guess_transaction_fails(self):
        self.data_manager.increment_pending_multiplier("1", 0.2)
        powerups = PowerUpManager(self.player_manager, self.data_manager, make_config())
        handler = GuessHandler(
            self.data_manager,
            self.player_manager,
            self.handler.daily_q,
            self.daily_question_id,
            {"powerup": powerups},
            config=make_config(),
        )

        def fail_after_rest_transition(*args, **kwargs):
            self.assertTrue(powerups.daily_state["1"].is_correct)
            self.assertGreater(powerups.daily_state["1"].score_earned, 0)
            self.db.execute_update("INSERT INTO missing_table VALUES (1)")

        with patch.object(
            self.data_manager,
            "log_powerup_usage",
            side_effect=fail_after_rest_transition,
        ):
            with self.assertRaises(sqlite3.OperationalError):
                handler.handle_guess("1", "Player", "Answer")

        player = self.player_manager.get_player("1")
        self.assertEqual(self.data_manager.read_guess_history("1"), [])
        self.assertEqual(player.score, 0)
        self.assertEqual(player.answer_streak, 0)
        self.assertEqual(player.pending_rest_multiplier, 0.2)
        self.assertEqual(powerups.daily_state, {})


if __name__ == "__main__":
    unittest.main()
