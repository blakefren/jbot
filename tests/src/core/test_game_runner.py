import unittest
from datetime import timedelta
from unittest.mock import patch, MagicMock, ANY

from data.readers.question import Question
from db.database import Database
from src.core.game_runner import GameRunner
from src.core.guess_handler import AlreadyAnsweredCorrectlyError
from src.core.data_manager import DataManager
from src.core.player_manager import PlayerManager
from src.core.subscriber import Subscriber
from src.core.state import DailyPlayerState


class GameRunnerTestBase(unittest.TestCase):
    """Real in-memory DB stack; only config, Discord and Gemini-backed selector are mocked."""

    def setUp(self):
        # PowerUpManager builds its own ConfigReader when none is injected.
        self.config_patchers = [
            patch("src.core.game_runner.ConfigReader"),
            patch("src.core.powerup.ConfigReader"),
        ]
        mock_config_classes = [p.start() for p in self.config_patchers]
        for patcher in self.config_patchers:
            self.addCleanup(patcher.stop)

        self.mock_config_instance = mock_config_classes[0].return_value
        mock_config_classes[1].return_value = self.mock_config_instance
        self.defaults = {
            "JBOT_RIDDLE_HISTORY_DAYS": "30",
            "JBOT_QUESTION_RETRIES": "10",
            "JBOT_EMOJI_FASTEST": "🥇",
            "JBOT_EMOJI_FASTEST_CSV": "🥇,🥈,🥉",
            "JBOT_BONUS_FASTEST_CSV": "10,5,1",
            "JBOT_BONUS_TRY_CSV": "20,10,5",
            "JBOT_BONUS_BEFORE_HINT": "10",
            "JBOT_BONUS_STREAK_PER_DAY": "5",
            "JBOT_BONUS_STREAK_CAP": "25",
            "JBOT_CROWD_WISDOM_DECAY_K": "1.15",
            "JBOT_EMOJI_FIRST_TRY": "🎯",
            "JBOT_EMOJI_BEFORE_HINT": "🧠",
            "JBOT_EMOJI_STREAK": "🔥",
            "JBOT_EMOJI_STREAK_BROKEN": "💔",
            "JBOT_EMOJI_JINXED": "🥶",
            "JBOT_EMOJI_SILENCED": "🤐",
            "JBOT_EMOJI_STOLEN_FROM": "💸",
            "JBOT_EMOJI_STEALING": "💰",
            "JBOT_EMOJI_REST": "😴",
            "JBOT_PLAYER_ROLE_NAME": "Players",
            "JBOT_FIRST_PLACE_ROLE_NAME": "First Place",
            "JBOT_TIMEZONE": "UTC",
        }
        self.mock_config_instance.get.side_effect = lambda k, d=None: self.defaults.get(
            k, d
        )
        self.mock_config_instance.get_bool.side_effect = lambda k, d=False: (
            str(self.defaults.get(k)).lower() == "true" if k in self.defaults else d
        )
        self.mock_config_instance.is_seasons_enabled.return_value = False
        self.mock_config_instance.get_season_mode.return_value = "calendar"
        self.mock_config_instance.get_season_auto_create.return_value = True
        self.mock_config_instance.get_season_announce_end.return_value = True
        self.mock_config_instance.get_season_announce_start.return_value = True
        self.mock_config_instance.get_season_trophy_positions.return_value = 3
        self.mock_config_instance.get_season_reminder_days.return_value = 5
        self.mock_config_instance.get_season_duration_days.return_value = 30

        self.db = Database(":memory:")
        self.addCleanup(self.db.close)
        self.data_manager = DataManager(self.db)
        self.player_manager = PlayerManager(self.data_manager)
        self.today = self.data_manager.get_today().isoformat()

        # Question selection is backed by files/Gemini, so it stays a mock.
        self.mock_question_selector = MagicMock()
        self.mock_question_selector.get_hint_from_gemini.return_value = None
        self.mock_question = Question(
            question="Test Question",
            answer="Test Answer",
            category="Test Category",
            clue_value=100,
        )
        self.mock_question_selector.get_random_question.return_value = (
            self.mock_question
        )
        self.mock_question_selector.questions = {"qid1": self.mock_question}

        self.game_runner = self._build_runner()

    def _build_runner(self) -> GameRunner:
        return GameRunner(
            self.mock_question_selector,
            self.data_manager,
            player_manager=self.player_manager,
        )

    def _add_player(
        self,
        player_id,
        name,
        score=0,
        streak=0,
        pending_rest_multiplier=None,
        guess_for=None,
        correct=False,
        at=None,
    ):
        """Create a player; optionally log one guess so they appear on leaderboards."""
        self.data_manager.create_player(player_id, name)
        stats = {"score": score, "answer_streak": streak}
        if pending_rest_multiplier is not None:
            stats["pending_rest_multiplier"] = pending_rest_multiplier
        self.data_manager.update_lifetime_stats(player_id, **stats)
        if guess_for is not None:
            self._guess(player_id, name, guess_for, correct=correct, at=at)

    def _activate_question(self, question=None) -> int:
        """Log a question for today and point the runner at it."""
        question = question or self.mock_question
        daily_question_id = self.data_manager.log_daily_question(question)
        _, _, question_db_id = self.data_manager.get_todays_daily_question()
        self.game_runner.daily_q = question
        self.game_runner.daily_question_id = daily_question_id
        self.game_runner.question_db_id = question_db_id
        return daily_question_id

    def _guess(
        self, player_id, name, daily_question_id, text=None, correct=True, at=None
    ):
        if text is None:
            text = self.mock_question.answer if correct else "wrong guess"
        self.data_manager.log_player_guess(
            player_id, name, daily_question_id, text, correct
        )
        if at:
            self.db.execute_update(
                "UPDATE guesses SET guessed_at = ? WHERE id = (SELECT MAX(id) FROM guesses)",
                (f"{self.today} {at}",),
            )

    def _set_hint_sent_at(self, at):
        self.data_manager.log_messaging_event(
            "outgoing", "Discord", "c", "morning", "morning_message"
        )
        self.data_manager.log_messaging_event(
            "outgoing", "Discord", "c", "reminder", "reminder_message"
        )
        self.db.execute_update(
            "UPDATE messages SET timestamp = ? WHERE status = 'morning_message'",
            (f"{self.today} 08:00:00",),
        )
        self.db.execute_update(
            "UPDATE messages SET timestamp = ? WHERE status = 'reminder_message'",
            (f"{self.today} {at}",),
        )

    def _count(self, table: str) -> int:
        return self.db.execute_query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]

    def _stored_hint(self):
        question, _, _ = self.data_manager.get_todays_daily_question()
        return question.hint

    @staticmethod
    def _line(text, name):
        return next((line for line in text.split("\n") if name in line), None)


class TestGameRunner(GameRunnerTestBase):
    def test_get_evening_message_content_with_guild_nicknames(self):
        """Test evening message uses server nicknames if guild is provided."""
        daily_question_id = self._activate_question()
        self._guess("111", "Alice", daily_question_id, "Test Answer", True)
        self._guess("222", "Bob", daily_question_id, "some guess", False)

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

    def test_initialization(self):
        """Test GameRunner initialization."""
        self.assertIn("powerup", self.game_runner.managers)
        self.assertEqual(
            self.game_runner.question_selector, self.mock_question_selector
        )
        self.assertEqual(self.game_runner.subscribed_contexts, set())
        self.assertIsNone(self.game_runner.daily_q)

    def test_initialization_loads_persisted_subscribers(self):
        subscriber = Subscriber(42, "Alice", False)
        self.data_manager.save_subscriber(subscriber)

        runner = self._build_runner()

        self.assertEqual(runner.subscribed_contexts, {subscriber})

    def test_set_daily_question(self):
        """Test setting the daily question."""
        self.game_runner.set_daily_question()

        self.mock_question_selector.get_random_question.assert_called_once()
        self.assertEqual(self.game_runner.daily_q.question, "Test Question")
        question, daily_question_id, question_db_id = (
            self.data_manager.get_todays_daily_question()
        )
        self.assertEqual(question.answer, "Test Answer")
        self.assertEqual(self.game_runner.daily_question_id, daily_question_id)
        self.assertEqual(self.game_runner.question_db_id, question_db_id)

    def test_set_daily_question_on_restart(self):
        """Test setting the daily question on restart when one already exists."""
        existing_id = self.data_manager.log_daily_question(self.mock_question)
        _, _, existing_db_id = self.data_manager.get_todays_daily_question()

        self.game_runner.set_daily_question()

        # Ensure we didn't try to select a new question
        self.mock_question_selector.get_random_question.assert_not_called()
        self.assertEqual(self._count("daily_questions"), 1)
        self.assertEqual(self.game_runner.daily_q.question, "Test Question")
        self.assertEqual(self.game_runner.daily_question_id, existing_id)
        self.assertEqual(self.game_runner.question_db_id, existing_db_id)

    def test_set_daily_question_on_restart_restores_guess_state(self):
        daily_question_id = self._activate_question()
        self._add_player("1", "Alice", guess_for=daily_question_id, correct=True)
        self.game_runner.daily_q = None
        self.game_runner.daily_question_id = None

        self.game_runner.set_daily_question()

        state = self.game_runner.managers["powerup"].daily_state["1"]
        self.assertTrue(state.is_correct)

    def test_add_and_remove_subscriber(self):
        """Test adding and removing a subscriber."""
        subscriber = Subscriber(7, "Alice", False)

        self.game_runner.add_subscriber(subscriber)
        self.assertIn(subscriber, self.game_runner.subscribed_contexts)
        self.assertIn(subscriber, self.data_manager.get_all_subscribers())

        self.game_runner.remove_subscriber(subscriber)
        self.assertNotIn(subscriber, self.game_runner.subscribed_contexts)
        self.assertNotIn(subscriber, self.data_manager.get_all_subscribers())

    def test_format_question_and_answer(self):
        """Test the formatting of questions and answers."""
        formatted_q = self.game_runner.format_question(self.mock_question)
        self.assertIn(self.mock_question.question, formatted_q)
        self.assertIn(self.mock_question.category, formatted_q)
        self.assertIn(str(self.mock_question.clue_value), formatted_q)

        formatted_a = self.game_runner.format_answer(self.mock_question)
        self.assertIn(self.mock_question.answer, formatted_a)
        self.assertIn("||", formatted_a)  # Spoiler tags

    def test_format_answer_looks_up_alternatives_by_question_id(self):
        self._activate_question()
        self.data_manager.add_alternative_answer(
            self.game_runner.question_db_id, "Alt Answer", "admin"
        )
        # A different id must not be mistaken for the question id.
        self.game_runner.daily_question_id = self.game_runner.question_db_id + 100

        formatted = self.game_runner.format_answer(self.mock_question)

        self.assertIn("Alt Answer", formatted)

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
        daily_question_id = self._activate_question()
        self._add_player("1", "Player1", guess_for=daily_question_id)
        self._add_player("2", "Player2")

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

    def test_get_reminder_message_content_no_daily_question(self):
        """Test get_reminder_message_content when no daily question is set."""
        self.game_runner.daily_q = None
        result = self.game_runner.get_reminder_message_content(tag_unanswered=True)
        self.assertEqual(result, "No question to remind about.")

    def test_end_daily_game(self):
        """Test ending the daily game resets state and streaks."""
        self._add_player("1", "Alice", score=100, streak=5)
        self._add_player("2", "Bob", score=100, streak=3, pending_rest_multiplier=1.5)
        daily_question_id = self._activate_question()
        powerup_manager = self.game_runner.managers["powerup"]
        powerup_manager.daily_state["1"] = DailyPlayerState(is_correct=True)

        self.game_runner.end_daily_game()

        self.assertIsNone(self.game_runner.daily_q)
        self.assertIsNone(self.game_runner.daily_question_id)
        self.assertEqual(powerup_manager.daily_state, {})
        # Reducer settlement resets only the player who missed the day.
        self.assertEqual(self.data_manager.get_player("1").answer_streak, 5)
        self.assertEqual(self.data_manager.get_player("2").answer_streak, 0)
        # Stale rest multipliers were expired
        self.assertEqual(self.data_manager.get_pending_multiplier("2"), 0.0)
        self.assertEqual(self._count("daily_questions"), 1)
        self.assertEqual(
            daily_question_id, self.data_manager.get_todays_daily_question()[1]
        )

    def test_end_daily_game_keeps_streak_of_resting_player(self):
        self._add_player("1", "Alice", streak=4)
        daily_question_id = self._activate_question()
        self.data_manager.log_powerup_usage("1", "rest", None, daily_question_id)
        self.game_runner.managers["powerup"].daily_state["1"] = DailyPlayerState(
            is_resting=True
        )

        self.game_runner.end_daily_game()

        self.assertEqual(self.data_manager.get_player("1").answer_streak, 4)

    def test_get_evening_message_content(self):
        """Test generating the evening message content with deduplicated, sorted, and bolded guesses."""
        daily_question_id = self._activate_question()
        other_day_id = self.data_manager.log_daily_question(
            Question("Other Q", "Other A", "Cat"), force_new=True
        )
        self._guess("333", "Charlie", daily_question_id, "wrong answer", False)
        self._guess("111", "Alice", daily_question_id, "Test Answer", True)
        self._guess("111", "Alice", daily_question_id, "another guess", False)
        self._guess("111", "Alice", daily_question_id, "another guess", False)
        self._guess("222", "Bob", daily_question_id, "some guess", False)
        # Another day's guess for Alice
        self._guess("111", "Alice", other_day_id, "yesterday's guess", False)

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
        self._activate_question()
        player_id = 123

        is_correct, _, _, _ = self.game_runner.handle_guess(
            player_id, "Test Player", "Test Answer"
        )
        self.assertTrue(is_correct)

        with self.assertRaises(AlreadyAnsweredCorrectlyError):
            self.game_runner.handle_guess(player_id, "Test Player", "Test Answer")

    def test_handle_guess(self):
        """Test handling a player's guess."""
        self.game_runner.set_daily_question()
        player_id, player_name = 123, "Test Guesser"

        is_correct, num_guesses, points, bonuses = self.game_runner.handle_guess(
            player_id, player_name, "test answer"
        )
        self.assertTrue(is_correct)
        self.assertEqual(num_guesses, 1)
        self.assertGreater(points, 0)
        self.assertEqual(self.data_manager.get_player("123").score, points)
        guesses = self.data_manager.read_guess_history(user_id="123")
        self.assertEqual(len(guesses), 1)
        self.assertTrue(guesses[0]["is_correct"])

        # No daily question
        self.game_runner.daily_q = None
        is_correct, num_guesses, points, bonuses = self.game_runner.handle_guess(
            player_id, player_name, "any answer"
        )
        self.assertFalse(is_correct)
        self.assertEqual(num_guesses, 0)
        self.assertEqual(self._count("guesses"), 1)

    def test_get_scores_leaderboard(self):
        """Test generating the scores leaderboard."""
        daily_question_id = self._activate_question()
        self._add_player("1", "Alice", score=10, guess_for=daily_question_id)
        self._add_player("2", "Bob", score=5, guess_for=daily_question_id)

        leaderboard = self.game_runner.get_scores_leaderboard()
        self.assertIn("🏆", leaderboard)
        self.assertIn("Player", leaderboard)
        self.assertIn("pts", leaderboard)
        # Streak emoji is now its own column header
        self.assertIn("🔥", leaderboard)
        self.assertIn("Alice", leaderboard)
        self.assertIn("Bob", leaderboard)
        self.assertTrue(leaderboard.find("Alice") < leaderboard.find("Bob"))

    def test_get_scores_leaderboard_with_guild(self):
        """Test generating the scores leaderboard with a guild to resolve names."""
        daily_question_id = self._activate_question()
        self._add_player("1", "OldNameAlice", score=10, guess_for=daily_question_id)
        self._add_player("2", "Bob", score=5, guess_for=daily_question_id)

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
        daily_question_id = self._activate_question()
        self._add_player("1", "OldNameAlice", score=10, guess_for=daily_question_id)

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
        daily_question_id = self._activate_question()
        # Alice and Charlie answered correctly today (so their streaks show).
        self._add_player(
            "1",
            "Alice",
            score=100,
            streak=3,
            guess_for=daily_question_id,
            correct=True,
            at="10:00:00",
        )
        self._add_player(
            "2", "Bob", score=90, streak=0, guess_for=daily_question_id, correct=False
        )
        self._add_player(
            "3",
            "Charlie",
            score=80,
            streak=5,
            guess_for=daily_question_id,
            correct=True,
            at="10:05:00",
        )

        leaderboard = self.game_runner.get_scores_leaderboard(show_daily_bonuses=True)

        self.assertIn("Alice", leaderboard)
        self.assertIn("Bob", leaderboard)
        self.assertIn("Charlie", leaderboard)
        # Streaks now appear as numbers in their own column, not combined with emoji
        alice_line = self._line(leaderboard, "Alice")
        charlie_line = self._line(leaderboard, "Charlie")
        bob_line = self._line(leaderboard, "Bob")
        self.assertIsNotNone(alice_line)
        self.assertIn(" 3 ", alice_line)  # streak column value
        self.assertIn(" 5 ", charlie_line)  # streak column value
        # Bob has no streak — streak column should be blank for Bob
        self.assertNotIn(" 1 ", bob_line)  # streak of 0 not shown

    def test_get_scores_leaderboard_broken_streak(self):
        """Test that players who had a streak but missed today show a broken streak."""
        daily_question_id = self._activate_question()
        self._add_player(
            "1",
            "Alice",
            score=100,
            streak=3,
            guess_for=daily_question_id,
            correct=True,
        )
        # Bob had a streak of 4 but won't keep it (wrong guess only)
        self._add_player(
            "2", "Bob", score=90, streak=4, guess_for=daily_question_id, correct=False
        )

        leaderboard = self.game_runner.get_scores_leaderboard(show_daily_bonuses=True)

        alice_line = self._line(leaderboard, "Alice")
        bob_line = self._line(leaderboard, "Bob")
        self.assertIsNotNone(alice_line)
        self.assertIsNotNone(bob_line)
        # Alice has an active streak — shown as a plain number
        self.assertIn(" 3", alice_line)
        # Bob's streak is broken — shown with just the broken emoji, no number
        self.assertIn("💔", bob_line)
        self.assertNotIn("4", bob_line)
        # Alice's line should not have the broken emoji
        self.assertNotIn("💔", alice_line)

    def test_get_player_history(self):
        """Test generating a player's history."""
        daily_question_id = self._activate_question()
        self._add_player("123", "Alice", score=300)
        for correct in (True, False, True, True):
            self._guess("123", "Alice", daily_question_id, correct=correct)

        history = self.game_runner.get_player_history(123, "Alice")
        self.assertIn("-- Your stats, Alice --", history)
        self.assertIn("Score:         300", history)
        self.assertIn("Streak:        0 day(s)", history)
        self.assertIn("Correct:       3/4 (75.0%)", history)

    def test_get_scores_leaderboard_alphabetical_tie(self):
        """Test that players with the same score are sorted alphabetically."""
        daily_question_id = self._activate_question()
        self._add_player("1", "Charlie", score=10, guess_for=daily_question_id)
        self._add_player("2", "Alice", score=10, guess_for=daily_question_id)
        self._add_player("3", "Bob", score=5, guess_for=daily_question_id)

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
        question_without_hint = Question(
            question="Test Q", answer="Test A", category="Test C"
        )
        self.assertIsNone(question_without_hint.hint)

        self.mock_question_selector.get_random_question.return_value = (
            question_without_hint
        )
        self.mock_question_selector.get_hint_from_gemini.return_value = "Generated Hint"

        self.game_runner.set_daily_question()

        # Always attempts generation
        self.mock_question_selector.get_hint_from_gemini.assert_called_once_with(
            question_without_hint
        )
        self.assertEqual(self.game_runner.daily_q.hint, "Generated Hint")
        self.assertEqual(self._count("daily_questions"), 1)
        self.assertEqual(self._stored_hint(), "Generated Hint")

    def test_set_daily_question_hint_generation_fails_gracefully(self):
        """Test that hint generation failure doesn't stop question selection."""
        question_without_hint = Question(
            question="Test Q", answer="Test A", category="Test C"
        )
        self.mock_question_selector.get_random_question.return_value = (
            question_without_hint
        )
        # Simulate Gemini failure
        self.mock_question_selector.get_hint_from_gemini.return_value = None

        self.game_runner.set_daily_question()

        # Always attempts generation
        self.mock_question_selector.get_hint_from_gemini.assert_called_once()
        self.assertIsNone(self.game_runner.daily_q.hint)  # No fallback, hint stays None
        self.assertEqual(self._count("daily_questions"), 1)  # Still logs

    def test_set_daily_question_with_existing_hint(self):
        """Test that a hint is always generated, overwriting existing hint."""
        question_with_hint = Question(
            question="Test Q", answer="Test A", category="Test C", hint="Existing Hint"
        )
        self.mock_question_selector.get_random_question.return_value = (
            question_with_hint
        )
        self.mock_question_selector.get_hint_from_gemini.return_value = (
            "New Generated Hint"
        )

        self.game_runner.set_daily_question()

        # Always generates, overwrites existing
        self.mock_question_selector.get_hint_from_gemini.assert_called_once()
        self.assertEqual(self.game_runner.daily_q.hint, "New Generated Hint")
        self.assertEqual(self._stored_hint(), "New Generated Hint")

    def test_reset_daily_question(self):
        """Test resetting the daily question to a new one."""
        self._add_player("1", "Alice", score=50)
        old_daily_question_id = self._activate_question()
        new_question = Question(
            question="New Question",
            answer="New Answer",
            category="New Cat",
            clue_value=200,
        )
        for used in (Question("Used 1", "A1", "C"), Question("Used 2", "A2", "C")):
            self.data_manager.log_daily_question(used, mark_as_used_only=True)
        used_hashes = self.data_manager.get_used_question_hashes()
        self.assertGreaterEqual(len(used_hashes), 3)
        self.mock_question_selector.get_random_question.return_value = new_question

        result = self.game_runner.reset_daily_question()

        self.assertTrue(result)
        self.assertEqual(self.game_runner.daily_q.question, "New Question")
        self.assertGreater(self.game_runner.daily_question_id, old_daily_question_id)
        self.assertEqual(
            self.game_runner.daily_question_id,
            self.data_manager.get_todays_daily_question()[1],
        )
        self.assertEqual(self._count("daily_questions"), 2)
        self.mock_question_selector.get_random_question.assert_called_once_with(
            exclude_hashes=used_hashes, previous_answers=ANY
        )

    def test_reset_daily_question_no_question_available(self):
        """Test reset_daily_question when no question is available."""
        self.mock_question_selector.get_random_question.return_value = None

        result = self.game_runner.reset_daily_question()

        self.assertFalse(result)
        self.assertEqual(self._count("daily_questions"), 0)

    def test_reset_daily_question_log_fails(self):
        """Test reset_daily_question when logging fails."""
        new_question = Question(question="Q", answer="A", category="C")
        self.mock_question_selector.get_random_question.return_value = new_question

        # Failure injection: the rest of the stack stays real.
        with patch.object(self.data_manager, "log_daily_question", return_value=None):
            result = self.game_runner.reset_daily_question()

        self.assertFalse(result)
        self.assertIsNone(self.data_manager.get_todays_daily_question())

    def test_set_daily_question_hint_generation_exception(self):
        """Test hint generation handles exceptions gracefully with no fallback."""
        question_no_hint = Question(question="Q", answer="A", category="C")
        self.mock_question_selector.get_random_question.return_value = question_no_hint
        self.mock_question_selector.get_hint_from_gemini.side_effect = Exception(
            "API Error"
        )

        self.game_runner.set_daily_question()

        # Should not raise, question should still be set, no hint (no fallback available)
        self.assertEqual(self.game_runner.daily_q.question, "Q")
        self.assertIsNone(self.game_runner.daily_q.hint)
        self.assertEqual(self._count("daily_questions"), 1)

    def test_set_daily_question_hint_generation_exception_with_fallback(self):
        """Test hint generation falls back to original hint when exception occurs."""
        question_with_hint = Question(
            question="Q", answer="A", category="C", hint="Original Hint"
        )
        self.mock_question_selector.get_random_question.return_value = (
            question_with_hint
        )
        self.mock_question_selector.get_hint_from_gemini.side_effect = Exception(
            "API Error"
        )

        self.game_runner.set_daily_question()

        # Should not raise, question should still be set with original hint
        self.assertEqual(self.game_runner.daily_q.question, "Q")
        self.assertEqual(self.game_runner.daily_q.hint, "Original Hint")
        self.assertEqual(self._stored_hint(), "Original Hint")

    def test_set_daily_question_hint_generation_returns_none_with_fallback(self):
        """Test hint generation falls back to original hint when it returns None."""
        question_with_hint = Question(
            question="Q", answer="A", category="C", hint="Original Hint"
        )
        self.mock_question_selector.get_random_question.return_value = (
            question_with_hint
        )
        self.mock_question_selector.get_hint_from_gemini.return_value = None

        self.game_runner.set_daily_question()

        # Should keep original hint when generation returns None
        self.assertEqual(self.game_runner.daily_q.hint, "Original Hint")
        self.assertEqual(self._stored_hint(), "Original Hint")

    def test_set_daily_question_fallback_on_log_none(self):
        """Test that set_daily_question falls back to get_todays_daily_question when log returns None."""
        question_with_hint = Question(question="Q", answer="A", category="C", hint="H")
        self.mock_question_selector.get_random_question.return_value = (
            question_with_hint
        )
        real_log = self.data_manager.log_daily_question

        # Failure injection: the row is written but the id is not returned.
        def log_without_id(question, force_new=False, mark_as_used_only=False):
            real_log(question, force_new=force_new)

        with patch.object(
            self.data_manager, "log_daily_question", side_effect=log_without_id
        ):
            self.game_runner.set_daily_question()

        _, stored_id, _ = self.data_manager.get_todays_daily_question()
        self.assertEqual(self.game_runner.daily_question_id, stored_id)

    def test_initialization_creates_season_manager(self):
        """Test that GameRunner creates a SeasonManager on init."""
        from src.core.season_manager import SeasonManager

        self.assertIsInstance(self.game_runner.season_manager, SeasonManager)

    def test_build_guess_handler_passes_season_manager(self):
        """Test that _build_guess_handler wires season_manager through to GuessHandler."""
        self.game_runner._build_guess_handler()
        self.assertIs(
            self.game_runner.guess_handler.season_manager,
            self.game_runner.season_manager,
        )

    def _create_season(self, start_offset_days: int, end_offset_days: int) -> int:
        today = self.game_runner.season_manager._today()
        return self.data_manager.create_season(
            "Existing Season",
            (today + timedelta(days=start_offset_days)).isoformat(),
            (today + timedelta(days=end_offset_days)).isoformat(),
        )

    def _enable_seasons(self):
        self.mock_config_instance.is_seasons_enabled.return_value = True
        self.game_runner = self._build_runner()

    def test_set_daily_question_calls_season_transition_when_enabled(self):
        """Test that set_daily_question triggers season transition check when seasons are enabled."""
        self._enable_seasons()
        expired_id = self._create_season(-35, -1)

        self.game_runner.set_daily_question()

        current = self.data_manager.get_current_season()
        self.assertNotEqual(current.season_id, expired_id)
        self.assertFalse(self.data_manager.get_season_by_id(expired_id).is_active)
        self.assertIsNotNone(self.data_manager.get_todays_daily_question())

    def test_set_daily_question_skips_season_transition_when_disabled(self):
        """Test that set_daily_question skips season logic when seasons are disabled."""
        expired_id = self._create_season(-35, -1)

        self.game_runner.set_daily_question()

        self.assertEqual(self._count("seasons"), 1)
        self.assertEqual(self.data_manager.get_current_season().season_id, expired_id)

    def test_pending_season_announcements_populated_on_transition(self):
        """On a season transition only the start announcement is queued (end announcement
        now fires via pending_evening_announcements on the last day)."""
        self._enable_seasons()
        self._create_season(-35, -1)

        self.game_runner.set_daily_question()

        # Only the new-season start message is queued; end announcement fires in evening
        new_season = self.data_manager.get_current_season()
        self.assertEqual(len(self.game_runner.pending_season_announcements), 1)
        self.assertIn(
            new_season.season_name, self.game_runner.pending_season_announcements[0]
        )

    def test_pending_season_announcements_empty_when_no_transition(self):
        """No announcements queued when season is still active and no reminder fires."""
        self._enable_seasons()
        self._create_season(-5, 20)

        # Not a reminder day (20 days left, reminder at 5) and not expired
        self.game_runner.set_daily_question()

        self.assertEqual(self.game_runner.pending_season_announcements, [])
        self.assertIsNone(self.game_runner.pending_morning_note)

    def test_get_scores_leaderboard_no_scores(self):
        """Test get_scores_leaderboard when there are no player scores."""
        result = self.game_runner.get_scores_leaderboard()
        self.assertEqual(result, "No scores available yet.")

    def test_get_scores_leaderboard_guild_exception(self):
        """Test get_scores_leaderboard handles guild member lookup exceptions."""
        daily_question_id = self._activate_question()
        self._add_player("1", "Alice", score=100, guess_for=daily_question_id)

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
        daily_question_id = self._activate_question()
        self._guess("111", "Alice", daily_question_id, "answer", True)

        mock_guild = MagicMock()
        mock_guild.get_member.side_effect = Exception("Guild error")

        with patch("src.core.game_runner.logging"):
            content = self.game_runner.get_evening_message_content(guild=mock_guild)

        # Should fall back to stored name
        self.assertIn("**Alice**", content)

    def _setup_crowd_wisdom_day(self):
        """Alice solved (earned 120, already persisted), Bob guessed wrong."""
        self._add_player("111", "Alice", score=100)
        self._add_player("222", "Bob", score=100)
        daily_question_id = self._activate_question()
        self.player_manager.update_score("111", 120)
        self.game_runner.managers["powerup"].daily_state = {
            "111": DailyPlayerState(is_correct=True, score_earned=120),
            "222": DailyPlayerState(guesses_count=1),
        }
        return daily_question_id

    def _crowd_wisdom_usages(self, daily_question_id):
        return [
            u
            for u in self.data_manager.get_powerup_usages_for_question(
                daily_question_id
            )
            if u["powerup_type"] == "crowd_wisdom"
        ]

    def test_apply_crowd_wisdom_bonus(self):
        daily_question_id = self._setup_crowd_wisdom_day()

        summary = self.game_runner.apply_crowd_wisdom_bonus()

        self.assertEqual(summary["multiplier"], 1.0)
        self.assertEqual(summary["total_bonus_points"], 120)
        self.assertEqual(self.data_manager.get_player("111").score, 340)
        self.assertEqual(self.data_manager.get_player("222").score, 100)
        usages = self._crowd_wisdom_usages(daily_question_id)
        self.assertEqual([u["user_id"] for u in usages], ["111"])
        self.assertEqual(
            self.data_manager.get_crowd_wisdom_awarded_user_ids(daily_question_id),
            {"111"},
        )

    def test_apply_crowd_wisdom_bonus_skips_already_awarded_users(self):
        daily_question_id = self._setup_crowd_wisdom_day()
        self.data_manager.log_powerup_usage(
            "111", "crowd_wisdom", None, daily_question_id
        )

        summary = self.game_runner.apply_crowd_wisdom_bonus()

        self.assertEqual(summary["multiplier"], 1.0)
        self.assertEqual(self.data_manager.get_player("111").score, 220)
        self.assertEqual(len(self._crowd_wisdom_usages(daily_question_id)), 1)

    def test_get_evening_message_content_includes_crowd_wisdom_line(self):
        self._activate_question()
        self.game_runner._crowd_wisdom_summary = {
            "multiplier": 0.316,
            "correct_solvers": 2,
            "active_participants": 5,
        }

        content = self.game_runner.get_evening_message_content()
        self.assertIn("Crowd Wisdom Bonus: +32% (solvers 2/5)", content)

    def test_get_player_history_no_history(self):
        """Test get_player_history when player has no history."""
        result = self.game_runner.get_player_history(123, "Alice")
        self.assertEqual(result, "No history found for Alice.")

    def test_get_subscribed_users(self):
        """Test getting subscribed users."""
        subscribers = {Subscriber(1, "A", False), Subscriber(2, "B", True)}
        self.game_runner.subscribed_contexts = subscribers
        result = self.game_runner.get_subscribed_users()
        self.assertEqual(result, subscribers)

    def test_get_scores_leaderboard_fastest_guesser(self):
        """Test that the fastest guesser is determined by guessed_at timestamp."""
        daily_question_id = self._activate_question()
        # Bob guessed first (earlier timestamp) but has higher ID
        self._add_player(
            "1",
            "Alice",
            score=100,
            guess_for=daily_question_id,
            correct=True,
            at="10:05:00",
        )
        self._add_player(
            "2",
            "Bob",
            score=100,
            guess_for=daily_question_id,
            correct=True,
            at="10:00:00",
        )

        leaderboard = self.game_runner.get_scores_leaderboard(show_daily_bonuses=True)

        # Bob should have the fastest guesser emoji (medal)
        self.assertIn("Bob", leaderboard)
        self.assertIn("🥇", leaderboard)

        # Ensure Alice is present
        self.assertIn("Alice", leaderboard)
        # But verify she doesn't have the medal emoji.
        alice_line = self._line(leaderboard, "Alice")
        self.assertIsNotNone(alice_line)
        self.assertNotIn("🥇", alice_line)
        # Alice is 2nd fastest and should now get 🥈
        self.assertIn("🥈", alice_line)

    def test_get_scores_leaderboard_second_and_third_fastest(self):
        """Test that 2nd and 3rd fastest guessers get their respective rank badges."""
        daily_question_id = self._activate_question()
        for pid, name, at in (
            ("1", "Alice", "10:05:00"),
            ("2", "Bob", "10:00:00"),
            ("3", "Charlie", "10:10:00"),
            ("4", "Dave", "10:15:00"),
        ):
            self._add_player(
                pid,
                name,
                score=100,
                guess_for=daily_question_id,
                correct=True,
                at=at,
            )

        leaderboard = self.game_runner.get_scores_leaderboard(show_daily_bonuses=True)

        bob_line = self._line(leaderboard, "Bob")
        alice_line = self._line(leaderboard, "Alice")
        charlie_line = self._line(leaderboard, "Charlie")
        dave_line = self._line(leaderboard, "Dave")

        # Bob is 1st fastest → 🥇
        self.assertIsNotNone(bob_line)
        self.assertIn("🥇", bob_line)

        # Alice is 2nd fastest → 🥈
        self.assertIsNotNone(alice_line)
        self.assertIn("🥈", alice_line)
        self.assertNotIn("🥇", alice_line)

        # Charlie is 3rd fastest → 🥉
        self.assertIsNotNone(charlie_line)
        self.assertIn("🥉", charlie_line)
        self.assertNotIn("🥇", charlie_line)

        # Dave is 4th — no fastest badge
        self.assertIsNotNone(dave_line)
        self.assertNotIn("🥇", dave_line)
        self.assertNotIn("🥈", dave_line)
        self.assertNotIn("🥉", dave_line)

    def test_get_scores_leaderboard_first_try_bonus(self):
        """Test that the first try bonus emoji is shown."""
        daily_question_id = self._activate_question()
        # Alice got it on the first try; Bob needed a second guess.
        self._add_player(
            "1", "Alice", score=100, guess_for=daily_question_id, correct=True
        )
        self._add_player(
            "2", "Bob", score=90, guess_for=daily_question_id, correct=False
        )
        self._guess("2", "Bob", daily_question_id, correct=True)

        leaderboard = self.game_runner.get_scores_leaderboard(show_daily_bonuses=True)

        # Alice should have the bullseye
        self.assertIn("Alice", leaderboard)
        self.assertIn("🎯", leaderboard)

        # Bob should not
        self.assertIn("Bob", leaderboard)
        bob_line = self._line(leaderboard, "Bob")
        self.assertIsNotNone(bob_line)
        self.assertNotIn("🎯", bob_line)

    def test_get_scores_leaderboard_emoji_width(self):
        """Test that emojis are counted as 2 characters wide for leaderboard spacing."""
        daily_question_id = self._activate_question()
        # Alice is fastest and first try; answered correctly so she keeps her streak
        self._add_player(
            "1",
            "Alice",
            score=100,
            streak=10,
            guess_for=daily_question_id,
            correct=True,
            at="10:00:00",
        )
        # Hint sent before the guess: no "before hint" bonus
        self._set_hint_sent_at("09:00:00")

        leaderboard = self.game_runner.get_scores_leaderboard(show_daily_bonuses=True)

        # We can check the divider line.
        # The divider line format is: f"{'-'*2} {'-'*max_name} {'-'*max_score} {'-'*max_streak} {'-'*max_badges}"
        # We need to extract the last part.

        lines = leaderboard.split("\n")
        # lines[0] is ```# ...
        # lines[1] is -- ...
        divider_line = lines[1]
        parts = divider_line.split(" ")
        # parts: ['--', '-----', '---', '--', '------']
        # last part is badges divider, second-to-last is streak divider
        badges_divider = parts[-1]
        streak_divider = parts[-2]

        # Badges divider: "Badges" header minimum = 6, so at least 6
        self.assertGreaterEqual(len(badges_divider), 6)
        # Streak divider: Alice has streak 10, so divider should be 2 wide (max of len("10"), 2)
        self.assertEqual(
            len(streak_divider),
            2,
            f"Expected streak divider length 2, got {len(streak_divider)}",
        )

    def test_get_scores_leaderboard_badge_order(self):
        """Test the order of badges in the leaderboard: Streak -> First Try -> Fastest."""
        daily_question_id = self._activate_question()
        # Alice is fastest and first try
        self._add_player(
            "1",
            "Alice",
            score=100,
            streak=5,
            guess_for=daily_question_id,
            correct=True,
            at="10:00:00",
        )

        leaderboard = self.game_runner.get_scores_leaderboard(show_daily_bonuses=True)

        # Expected badge order: First Try (🎯), Fastest (🥇)
        # Streak is now a standalone column, not a badge.
        # We check the relative positions in the string.
        streak_pos = leaderboard.find("🔥")
        first_try_pos = leaderboard.find("🎯")
        fastest_pos = leaderboard.find("🥇")

        self.assertNotEqual(streak_pos, -1)
        self.assertNotEqual(first_try_pos, -1)
        self.assertNotEqual(fastest_pos, -1)

        # streak emoji appears in the header column, before any badges
        self.assertLess(streak_pos, first_try_pos)
        self.assertLess(first_try_pos, fastest_pos)

    def test_get_scores_leaderboard_before_hint_bonus(self):
        """Test that the before hint bonus emoji is shown."""
        daily_question_id = self._activate_question()
        # Alice guessed before the hint; Bob after it.
        self._add_player(
            "1",
            "Alice",
            score=110,
            guess_for=daily_question_id,
            correct=True,
            at="10:00:00",
        )
        self._add_player(
            "2",
            "Bob",
            score=100,
            guess_for=daily_question_id,
            correct=True,
            at="13:00:00",
        )
        self._set_hint_sent_at("12:00:00")

        leaderboard = self.game_runner.get_scores_leaderboard(show_daily_bonuses=True)

        # Alice should have the brain emoji, Bob should not
        self.assertIn("🧠", self._line(leaderboard, "Alice"))
        self.assertNotIn("🧠", self._line(leaderboard, "Bob"))

    def test_handle_guess_no_question(self):
        self.game_runner.daily_q = None
        self.assertEqual(
            self.game_runner.handle_guess(1, "Player1", "test"),
            (False, 0, 0, []),
        )


class TestRegenerateHintIfMissing(GameRunnerTestBase):
    """Tests for GameRunner.regenerate_hint_if_missing."""

    def setUp(self):
        super().setUp()
        self.question = Question(
            question="What is 2+2?",
            answer="4",
            category="Math",
            hint=None,
        )

    def test_returns_false_when_no_daily_question(self):
        self.game_runner.daily_q = None
        result = self.game_runner.regenerate_hint_if_missing()
        self.assertFalse(result)
        self.mock_question_selector.get_hint_from_gemini.assert_not_called()

    def test_returns_true_when_hint_already_set(self):
        self.question.hint = "Existing hint"
        self.game_runner.daily_q = self.question
        result = self.game_runner.regenerate_hint_if_missing()
        self.assertTrue(result)
        self.mock_question_selector.get_hint_from_gemini.assert_not_called()

    def test_generates_and_persists_hint_when_missing(self):
        self._activate_question(self.question)
        self.mock_question_selector.get_hint_from_gemini.return_value = "New hint"

        result = self.game_runner.regenerate_hint_if_missing()

        self.assertTrue(result)
        self.assertEqual(self.question.hint, "New hint")
        self.assertEqual(self._stored_hint(), "New hint")

    def test_returns_false_when_gemini_returns_empty(self):
        self._activate_question(self.question)
        self.mock_question_selector.get_hint_from_gemini.return_value = None

        result = self.game_runner.regenerate_hint_if_missing()

        self.assertFalse(result)
        self.assertIsNone(self.question.hint)
        self.assertIsNone(self._stored_hint())

    def test_returns_false_on_exception(self):
        self._activate_question(self.question)
        self.mock_question_selector.get_hint_from_gemini.side_effect = Exception(
            "API Error"
        )

        result = self.game_runner.regenerate_hint_if_missing()

        self.assertFalse(result)
        self.assertIsNone(self._stored_hint())


if __name__ == "__main__":
    unittest.main()
