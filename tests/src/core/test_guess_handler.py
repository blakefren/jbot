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

        self.managers["test_manager"].on_guess.assert_called_once_with(
            player_id, player_name, guess, True
        )

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

        self.managers["test_manager"].on_guess.assert_called_once_with(
            player_id, player_name, guess, False
        )

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
            ("clokc", "clock", False),  # Now too distant (dist 2) under tightened rules
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
        # on_guess called twice (initial attempt + fallback attempt)
        self.assertEqual(mock_manager.on_guess.call_count, 2)

    def test_distance_limit_very_short_answer(self):
        """Test that very short answers (<=2 chars) require exact match."""
        # For answers <= 2 chars, distance limit is 0 (exact match required)
        self.assertTrue(self.guess_handler._is_correct_guess("ab", "ab"))
        self.assertFalse(self.guess_handler._is_correct_guess("ac", "ab"))

    def test_distance_limit_medium_answer(self):
        """Test distance limit for medium length answers (6-8 chars)."""
        # For 6-8 char answers, limit is 2
        self.assertTrue(
            self.guess_handler._is_correct_guess("testing", "testinx")
        )  # dist 1
        self.assertTrue(
            self.guess_handler._is_correct_guess("testing", "testixg")
        )  # dist 1
        self.assertFalse(
            self.guess_handler._is_correct_guess("testing", "texxxxx")
        )  # too distant

    def test_distance_limit_long_answer(self):
        """Test distance limit for longer answers (9-12 chars)."""
        # For 9-12 char answers, limit is 3
        self.assertTrue(
            self.guess_handler._is_correct_guess("programming", "programminx")
        )  # dist 1
        self.assertTrue(
            self.guess_handler._is_correct_guess("programming", "programxinx")
        )  # dist 2

    def test_distance_limit_very_long_answer(self):
        """Test distance limit for very long answers (>12 chars)."""
        # For >12 char answers, limit is 4
        answer = "extraordinary"  # 13 chars
        self.assertTrue(
            self.guess_handler._is_correct_guess("extraordinari", answer)
        )  # dist 1

    def test_numeric_strictness(self):
        """Test that numeric answers require exact matches."""
        # Exact match should still work
        self.assertTrue(self.guess_handler._is_correct_guess("150", "150"))

        # Close numbers should fail (Levenshtein distance is small, but strictness rejects it)
        self.assertFalse(self.guess_handler._is_correct_guess("250", "150"))  # dist 1
        self.assertFalse(self.guess_handler._is_correct_guess("151", "150"))  # dist 1
        self.assertFalse(self.guess_handler._is_correct_guess("15", "150"))  # dist 1

        # Normalization should still apply
        self.assertTrue(self.guess_handler._is_correct_guess("one", "1"))
        self.assertFalse(self.guess_handler._is_correct_guess("two", "1"))


if __name__ == "__main__":
    unittest.main()
