import unittest
from unittest.mock import MagicMock, patch
from src.core.guess_handler import GuessHandler, AlreadyAnsweredCorrectlyError
from data.readers.question import Question


class TestGuessHandler(unittest.TestCase):
    def setUp(self):
        self.data_manager = MagicMock()
        self.daily_question = Question(
            "Test Question", "Test Answer", "Test Category", 100, "Test Hint"
        )
        self.daily_question_id = 123

        self.player_manager = MagicMock()
        self.managers = {"player": self.player_manager, "test_manager": MagicMock()}

        # Mock can_answer for all managers
        self.managers["test_manager"].can_answer.return_value = (True, "")
        self.player_manager.can_answer.return_value = (True, "")

        self.guess_handler = GuessHandler(
            self.data_manager,
            self.player_manager,
            self.daily_question,
            self.daily_question_id,
            self.managers,
        )

    def test_handle_guess_correct(self):
        """Test handling a correct guess."""
        player_id = 1
        player_name = "PlayerOne"
        guess = "Test Answer"

        # No direct Player methods should be required; manager handles streaks
        self.player_manager.get_player.return_value = None
        self.data_manager.get_correct_guess_count.return_value = 1  # Not first

        # Mock so that get_player_guesses returns the guess we are making
        self.data_manager.read_guess_history.return_value = [
            {"daily_question_id": self.daily_question_id, "guess_text": guess}
        ]

        is_correct, num_guesses, points, bonuses = self.guess_handler.handle_guess(
            player_id, player_name, guess
        )

        self.assertTrue(is_correct)
        self.assertEqual(num_guesses, 1)
        self.data_manager.log_player_guess.assert_called_once_with(
            player_id, player_name, self.daily_question_id, guess.lower(), True
        )

        # Streak should be incremented here
        self.player_manager.increment_streak.assert_called_once()

        # Check that on_guess was called. Arguments are complex, so we just check it was called.
        self.managers["test_manager"].on_guess.assert_called_once()
        args, _ = self.managers["test_manager"].on_guess.call_args
        self.assertEqual(args[0], player_id)
        self.assertEqual(args[1], player_name)
        self.assertEqual(args[2], guess)
        self.assertEqual(args[3], True)
        # args[4] is points, args[5] is bonus_values

    def test_handle_guess_incorrect(self):
        """Test handling an incorrect guess."""
        player_id = 2
        player_name = "PlayerTwo"
        guess = "Wrong Answer"

        self.player_manager.get_player.return_value = None

        # Mock so that get_player_guesses returns the guess we are making
        self.data_manager.read_guess_history.return_value = [
            {"daily_question_id": self.daily_question_id, "guess_text": guess}
        ]

        is_correct, num_guesses, points, bonuses = self.guess_handler.handle_guess(
            player_id, player_name, guess
        )

        self.assertFalse(is_correct)
        self.assertEqual(num_guesses, 1)
        self.data_manager.log_player_guess.assert_called_once_with(
            player_id, player_name, self.daily_question_id, guess.lower(), False
        )

        # Verify streak logic
        self.player_manager.increment_streak.assert_not_called()

        self.managers["test_manager"].on_guess.assert_called_once()
        args, _ = self.managers["test_manager"].on_guess.call_args
        self.assertEqual(args[0], player_id)
        self.assertEqual(args[1], player_name)
        self.assertEqual(args[2], guess)
        self.assertEqual(args[3], False)

    def test_handle_guess_already_answered_correctly(self):
        """Test that an error is raised if a player has already answered correctly."""
        player_id = 3
        player_name = "PlayerThree"
        guess = "Another Answer"

        self.data_manager.read_guess_history.return_value = [
            {"daily_question_id": self.daily_question_id, "is_correct": True}
        ]

        with self.assertRaises(AlreadyAnsweredCorrectlyError):
            self.guess_handler.handle_guess(player_id, player_name, guess)

    def test_get_player_guesses(self):
        """Test retrieving a player's guesses for the current question."""
        player_id = 4
        self.data_manager.read_guess_history.return_value = [
            {"daily_question_id": self.daily_question_id, "guess_text": "guess1"},
            {"daily_question_id": self.daily_question_id, "guess_text": "guess2"},
            {"daily_question_id": 999, "guess_text": "old_guess"},  # Not for today
        ]

        guesses = self.guess_handler.get_player_guesses(player_id)
        self.assertEqual(len(guesses), 2)
        self.assertIn("guess1", guesses)
        self.assertIn("guess2", guesses)

    def test_has_answered_correctly_today_true(self):
        """Test checking if a player has answered correctly today when they have."""
        player_id = 5
        self.data_manager.read_guess_history.return_value = [
            {"daily_question_id": self.daily_question_id, "is_correct": True}
        ]

        self.assertTrue(self.guess_handler.has_answered_correctly_today(player_id))

    def test_has_answered_correctly_today_false(self):
        """Test checking if a player has answered correctly today when they have not."""
        player_id = 6
        self.data_manager.read_guess_history.return_value = [
            {"daily_question_id": self.daily_question_id, "is_correct": False}
        ]

        self.assertFalse(self.guess_handler.has_answered_correctly_today(player_id))

    def test_advanced_guess_checking(self):
        """Test the advanced guess checking logic with normalization and fuzzy matching."""
        # (guess, answer, expected_result)
        test_cases = [
            # Basic matches
            ("clock", "clock", True),  # Exact
            ("A Clock", "clock", True),  # Normalization (case, article)
            ("the clock", "clock", True),  # Stop word removal
            ("clock.", "clock", True),  # Punctuation
            # "Hack" attempts
            ("c", "clock", False),  # Too short
            (".", "clock", False),  # Normalized to empty
            ("o", "clock", False),  # Too short
            # Spell correction (fuzzy matching)
            ("clokc", "clock", True),  # Fuzzy (dist 2)
            ("clocc", "clock", True),  # Fuzzy (dist 1)
            ("clockk", "clock", True),  # Fuzzy (dist 1)
            ("klock", "clock", True),  # Fuzzy (dist 1)
            ("spnige", "sponge", True),  # Fuzzy (dist 2)
            ("splnge", "sponge", True),  # Fuzzy (dist 2)
            # Number/Word matching
            ("one", "1", True),  # Normalization
            ("1", "one", True),  # Normalization
            ("7", "seven", True),  # Normalization
            # Multi-word answers
            ("The Great Gatsby", "great gatsby", True),
            ("great gatsby", "The Great Gatsby", True),
            ("great gatsy", "The Great Gatsby", True),  # Fuzzy
        ]

        for guess, answer, expected in test_cases:
            with self.subTest(f"Guess: '{guess}', Answer: '{answer}'"):
                # Direct test of the internal method
                self.assertEqual(
                    self.guess_handler._is_correct_guess(guess, answer), expected
                )

    def test_normalize_empty_text(self):
        """Test that _normalize returns empty string for empty or None input."""
        self.assertEqual(self.guess_handler._normalize(""), "")
        self.assertEqual(self.guess_handler._normalize(None), "")

    def test_get_player_guesses_no_daily_question_id(self):
        """Test get_player_guesses returns empty list when no daily_question_id."""
        handler = GuessHandler(
            self.data_manager,
            self.player_manager,
            self.daily_question,
            daily_question_id=None,  # No daily question ID
            managers=self.managers,
        )
        result = handler.get_player_guesses(player_id=123)
        self.assertEqual(result, [])

    def test_has_answered_correctly_today_no_daily_question_id(self):
        """Test has_answered_correctly_today returns False when no daily_question_id."""
        handler = GuessHandler(
            self.data_manager,
            self.player_manager,
            self.daily_question,
            daily_question_id=None,  # No daily question ID
            managers=self.managers,
        )
        result = handler.has_answered_correctly_today(player_id=123)
        self.assertFalse(result)

    def test_handle_guess_no_daily_question(self):
        """Test handle_guess returns False when there's no daily question."""
        handler = GuessHandler(
            self.data_manager,
            self.player_manager,
            daily_question=None,  # No daily question
            daily_question_id=None,
            managers=self.managers,
        )
        result, num_guesses, points, bonuses = handler.handle_guess(
            123, "Player", "guess"
        )
        self.assertFalse(result)
        self.assertEqual(num_guesses, 0)

    def test_handle_guess_manager_on_guess_type_error_fallback(self):
        """Test manager on_guess falls back when TypeError is raised."""
        # Create a mock manager that raises TypeError on first call
        mock_manager = MagicMock()
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise TypeError("Wrong signature")
            # Second call (fallback) should succeed

        mock_manager.on_guess.side_effect = side_effect
        mock_manager.can_answer.return_value = (True, "")

        # Create a local player manager mock
        local_player_manager = MagicMock()
        # Mock get_player to return a player with answer_streak
        mock_player = MagicMock()
        mock_player.answer_streak = 1
        local_player_manager.get_player.return_value = mock_player
        local_player_manager.increment_streak.return_value = 2

        handler = GuessHandler(
            self.data_manager,
            local_player_manager,
            self.daily_question,
            self.daily_question_id,
            managers={"test": mock_manager},
        )

        self.data_manager.read_guess_history.return_value = []

        with patch("src.core.guess_handler.logging") as mock_logging:
            result, _, _, _ = handler.handle_guess(1, "Player", "Test Answer")

        # on_guess should have been called twice (initial + fallback)
        self.assertEqual(mock_manager.on_guess.call_count, 2)

    def test_handle_guess_manager_on_guess_both_fail(self):
        """Test manager on_guess gracefully handles when both calls fail."""
        mock_manager = MagicMock()
        mock_manager.on_guess.side_effect = TypeError("Wrong signature")
        mock_manager.can_answer.return_value = (True, "")

        # Create a local player manager mock
        local_player_manager = MagicMock()
        # Mock get_player to return a player with answer_streak
        mock_player = MagicMock()
        mock_player.answer_streak = 1
        local_player_manager.get_player.return_value = mock_player
        local_player_manager.increment_streak.return_value = 2

        handler = GuessHandler(
            self.data_manager,
            local_player_manager,
            self.daily_question,
            self.daily_question_id,
            managers={"test": mock_manager},
        )

        self.data_manager.read_guess_history.return_value = []

        with patch("src.core.guess_handler.logging"):
            result, num_guesses, _, _ = handler.handle_guess(1, "Player", "Test Answer")

        # Should not raise, just log error and continue
        self.assertTrue(result)  # Answer was still correct
        # on_guess called 3 times (initial + fallback + fallback 2)
        self.assertEqual(mock_manager.on_guess.call_count, 3)

    def test_handle_guess_streak_reset(self):
        """Test that streak is reset if last correct guess was not yesterday."""
        player_id = 1
        player_name = "PlayerOne"
        guess = "Test Answer"

        # Mock player with existing streak
        mock_player = MagicMock()
        mock_player.answer_streak = 5
        self.player_manager.get_player.return_value = mock_player

        # Mock last correct guess date to be 2 days ago
        from datetime import date, timedelta

        today = date.today()
        two_days_ago = today - timedelta(days=2)
        self.data_manager.get_last_correct_guess_date.return_value = two_days_ago

        # Mock guess history
        self.data_manager.read_guess_history.return_value = [
            {"daily_question_id": self.daily_question_id, "guess_text": guess}
        ]

        self.guess_handler.handle_guess(player_id, player_name, guess)

        # Streak should be reset
        self.player_manager.reset_streak.assert_called_once_with(str(player_id))
        # And then incremented
        self.player_manager.increment_streak.assert_called_once()

    def test_handle_guess_streak_continues(self):
        """Test that streak continues if last correct guess was yesterday."""
        player_id = 1
        player_name = "PlayerOne"
        guess = "Test Answer"

        # Mock player with existing streak
        mock_player = MagicMock()
        mock_player.answer_streak = 5
        self.player_manager.get_player.return_value = mock_player

        # Mock last correct guess date to be yesterday
        from datetime import date, timedelta

        today = date.today()
        yesterday = today - timedelta(days=1)
        self.data_manager.get_last_correct_guess_date.return_value = yesterday

        # Mock guess history
        self.data_manager.read_guess_history.return_value = [
            {"daily_question_id": self.daily_question_id, "guess_text": guess}
        ]

        self.guess_handler.handle_guess(player_id, player_name, guess)

        # Streak should NOT be reset
        self.player_manager.reset_streak.assert_not_called()
        # And then incremented
        self.player_manager.increment_streak.assert_called_once()

    def test_handle_guess_before_hint_bonus(self):
        """Test that bonus points are awarded if guess is before hint."""
        from datetime import datetime, time
        from zoneinfo import ZoneInfo

        # Setup timezone and times
        tz = ZoneInfo("UTC")
        reminder_time = time(12, 0, tzinfo=tz)

        # Create handler with reminder_time
        handler = GuessHandler(
            self.data_manager,
            self.player_manager,
            self.daily_question,
            self.daily_question_id,
            self.managers,
            reminder_time=reminder_time,
        )

        # Mock current time to be before reminder_time
        with patch("src.core.guess_handler.datetime") as mock_datetime:
            # Mock now() to return 10:00 AM
            mock_now = datetime(2023, 1, 1, 10, 0, tzinfo=tz)
            mock_datetime.now.return_value = mock_now

            # Mock other dependencies
            self.player_manager.get_player.return_value = None
            self.data_manager.get_correct_guess_count.return_value = 1
            self.data_manager.read_guess_history.return_value = []

            is_correct, num_guesses, points, bonuses = handler.handle_guess(
                1, "Player", "Test Answer"
            )

            self.assertTrue(is_correct)
            # Base points (100) + First Try (20) + Before Hint Bonus (10) = 130
            self.assertEqual(points, 130)
            self.assertTrue(any("Before hint!" in msg for msg in bonuses))

    def test_validation_logic(self):
        """Test the strict hierarchy of answer validation logic."""
        # (guess, answer, expected_result)
        cases = [
            # Step A: Exact Match & Normalization
            ("1", "1", True),
            ("one", "1", True),
            ("ONE", "1", True),
            ("  one  ", "1", True),
            # Step B: Standard Fuzzy Match (Typos)
            ("clokc", "clock", True),
            ("clock", "clokc", True),
            ("kitten", "sitting", False),  # Distance > 2
            # Step B Exception: Numeric Answers
            ("150", "650", False),  # Distance 1, but numeric answer
            ("10", "100", False),  # Distance 1, but numeric answer
            # Step B Safety Check: Multi-word semantic differences
            ("North America", "South America", False),  # Dist 2, but "North" != "South"
            (
                "New Yrok",
                "New York",
                True,
            ),  # Dist 2 (Lev), but "Yrok" is typo (DamLev 1)
            # Step C: Smart Token Match
            # Subset Match (Venn Diagram): Precision == 1.0 AND Recall >= 0.5
            ("Mountain Time", "Mountain Daylight Time", True),  # P=1.0, R=2/3=0.66
            ("Central Daylight Time", "Mountain Daylight Time", False),  # P=2/3, R=2/3
            # Superset Match (Over-answering): Recall == 1.0 AND len(answer) > 3
            ("Central Standard Time", "Central", True),  # R=1.0, AnsLen > 3
            ("Civil War", "War", False),  # R=1.0, but AnsLen=3 (not > 3)
            # Stop words
            ("The Beatles", "Beatles", True),
            ("A Tale of Two Cities", "Tale Two Cities", True),
            ("Virginia", "West Virginia", False),
            ("Dr.", "Dr. No", False),
            ("York", "New York", False),
            # TODO: address thse cases
            # ("carnivore", "carnivorous", True),
            # ("tape", "a stapler", False),
        ]

        for guess, answer, expected in cases:
            with self.subTest(guess=guess, answer=answer):
                result = self.guess_handler._is_correct_guess(guess, answer)
                self.assertEqual(
                    result, expected, f"Failed for guess='{guess}', answer='{answer}'"
                )


if __name__ == "__main__":
    unittest.main()
