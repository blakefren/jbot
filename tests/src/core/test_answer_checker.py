import unittest

from src.core.answer_checker import CRUCIAL_MODIFIERS, AnswerChecker


class TestAnswerCheckerNormalize(unittest.TestCase):
    def setUp(self):
        self.checker = AnswerChecker()

    def test_empty_string(self):
        self.assertEqual(self.checker.normalize(""), "")

    def test_none_input(self):
        self.assertEqual(self.checker.normalize(None), "")

    def test_lowercases(self):
        self.assertEqual(self.checker.normalize("HELLO"), "hello")

    def test_strips_whitespace(self):
        self.assertEqual(self.checker.normalize("  hello  "), "hello")

    def test_removes_punctuation(self):
        self.assertEqual(self.checker.normalize("hello."), "hello")
        self.assertEqual(self.checker.normalize("it's"), "its")

    def test_removes_stop_words(self):
        self.assertEqual(self.checker.normalize("the cat"), "cat")
        self.assertEqual(self.checker.normalize("a dog"), "dog")
        self.assertEqual(self.checker.normalize("an apple"), "apple")
        self.assertEqual(self.checker.normalize("lord of the rings"), "lord rings")

    def test_number_word_to_digit(self):
        for word, digit in [
            ("one", "1"),
            ("two", "2"),
            ("three", "3"),
            ("four", "4"),
            ("five", "5"),
            ("six", "6"),
            ("seven", "7"),
            ("eight", "8"),
            ("nine", "9"),
            ("ten", "10"),
        ]:
            with self.subTest(word=word):
                self.assertEqual(self.checker.normalize(word), digit)

    def test_number_word_in_phrase(self):
        self.assertEqual(self.checker.normalize("seven wonders"), "7 wonders")

    def test_collapses_multiple_spaces(self):
        self.assertEqual(self.checker.normalize("hello   world"), "hello world")

    def test_preserves_crucial_modifiers(self):
        # "north", "south", "east", "west", "new", "no" are NOT stop words
        self.assertIn("north", self.checker.normalize("north america"))
        self.assertIn("new", self.checker.normalize("new york"))


class TestAnswerCheckerGetAdaptiveLimit(unittest.TestCase):
    def setUp(self):
        self.checker = AnswerChecker()

    def test_very_short_returns_zero(self):
        self.assertEqual(self.checker.get_adaptive_limit("ab"), 0)
        self.assertEqual(self.checker.get_adaptive_limit("a"), 0)

    def test_short_word_returns_one(self):
        self.assertEqual(self.checker.get_adaptive_limit("cat"), 1)
        self.assertEqual(self.checker.get_adaptive_limit("hello"), 1)

    def test_long_word_returns_two(self):
        self.assertEqual(self.checker.get_adaptive_limit("python"), 2)
        self.assertEqual(self.checker.get_adaptive_limit("geography"), 2)


class TestAnswerCheckerIsTokenMatch(unittest.TestCase):
    def setUp(self):
        self.checker = AnswerChecker()

    def test_exact_match(self):
        self.assertTrue(self.checker.is_token_match("clock", "clock"))

    def test_one_edit_distance(self):
        self.assertTrue(self.checker.is_token_match("clocc", "clock"))

    def test_two_edit_distance_long(self):
        self.assertTrue(self.checker.is_token_match("clokc", "clock"))

    def test_too_many_edits_short_word(self):
        # "cat" has limit 1; "bat" is distance 1 → match; "bat" vs "cap" is distance 2 → no match
        self.assertFalse(self.checker.is_token_match("xyz", "cat"))

    def test_high_jaro_winkler_match(self):
        # "python" vs "pytohn" → jaro-winkler high
        self.assertTrue(self.checker.is_token_match("pytohn", "python"))

    def test_completely_different(self):
        self.assertFalse(self.checker.is_token_match("london", "paris"))


class TestAnswerCheckerSmartTokenMatch(unittest.TestCase):
    def setUp(self):
        self.checker = AnswerChecker()

    def test_subset_match_precision_1(self):
        # "Mountain Time" subset of "Mountain Daylight Time" → P=1.0, R=2/3
        self.assertTrue(
            self.checker.smart_token_match("mountain time", "mountain daylight time")
        )

    def test_superset_match_recall_1(self):
        # "Central Standard Time" contains "Central" → R=1.0, len("central") > 3
        self.assertTrue(
            self.checker.smart_token_match("central standard time", "central")
        )

    def test_superset_no_match_short_answer(self):
        # "Civil War" vs "War" → R=1.0, but len("war") == 3 (not > 3) → False
        self.assertFalse(self.checker.smart_token_match("civil war", "war"))

    def test_crucial_modifier_blocks_match(self):
        self.assertFalse(
            self.checker.smart_token_match("north america", "south america")
        )
        self.assertFalse(self.checker.smart_token_match("east river", "west river"))
        self.assertFalse(self.checker.smart_token_match("york", "new york"))

    def test_empty_guess(self):
        self.assertFalse(self.checker.smart_token_match("", "clock"))

    def test_empty_answer(self):
        self.assertFalse(self.checker.smart_token_match("clock", ""))

    def test_crucial_modifiers_constant_contents(self):
        self.assertIn("north", CRUCIAL_MODIFIERS)
        self.assertIn("south", CRUCIAL_MODIFIERS)
        self.assertIn("east", CRUCIAL_MODIFIERS)
        self.assertIn("west", CRUCIAL_MODIFIERS)
        self.assertIn("new", CRUCIAL_MODIFIERS)
        self.assertIn("no", CRUCIAL_MODIFIERS)


class TestAnswerCheckerIsCorrect(unittest.TestCase):
    """End-to-end tests for the full is_correct matching pipeline."""

    def setUp(self):
        self.checker = AnswerChecker()

    def test_exact_match(self):
        self.assertTrue(self.checker.is_correct("Paris", "Paris"))

    def test_case_insensitive(self):
        self.assertTrue(self.checker.is_correct("PARIS", "paris"))

    def test_article_removed(self):
        self.assertTrue(self.checker.is_correct("The Beatles", "Beatles"))

    def test_number_word_to_digit(self):
        self.assertTrue(self.checker.is_correct("four", "4"))
        self.assertTrue(self.checker.is_correct("42", "42"))

    def test_numeric_answer_requires_exact(self):
        self.assertFalse(self.checker.is_correct("150", "650"))
        self.assertFalse(self.checker.is_correct("10", "100"))

    def test_empty_guess_false(self):
        self.assertFalse(self.checker.is_correct("", "clock"))
        self.assertFalse(self.checker.is_correct(".", "clock"))

    def test_fuzzy_single_word(self):
        self.assertTrue(self.checker.is_correct("clokc", "clock"))
        self.assertTrue(self.checker.is_correct("clocc", "clock"))

    def test_multi_word_fuzzy(self):
        self.assertTrue(self.checker.is_correct("great gatsy", "The Great Gatsby"))

    def test_superset_accepted(self):
        self.assertTrue(self.checker.is_correct("George Washington", "washington"))

    def test_subset_accepted(self):
        self.assertTrue(self.checker.is_correct("washington", "George Washington"))

    def test_mismatch(self):
        self.assertFalse(self.checker.is_correct("London", "Paris"))
        self.assertFalse(self.checker.is_correct("100", "200"))
        self.assertFalse(self.checker.is_correct("New York", "Los Angeles"))

    def test_crucial_modifier_blocks(self):
        self.assertFalse(self.checker.is_correct("North America", "South America"))
        self.assertFalse(self.checker.is_correct("Virginia", "West Virginia"))
        self.assertFalse(self.checker.is_correct("York", "New York"))

    def test_validation_hierarchy(self):
        """Covers the full step-by-step validation logic described in the architecture."""
        cases = [
            # Exact match & normalization
            ("1", "1", True),
            ("one", "1", True),
            ("  one  ", "1", True),
            # Standard fuzzy
            ("clokc", "clock", True),
            ("kitten", "sitting", False),
            # Numeric answer is exact-only
            ("150", "650", False),
            ("10", "100", False),
            # Crucial modifier guard
            ("North America", "South America", False),
            ("New Yrok", "New York", True),  # Typo in "New" token, but "new" matches
            # Subset match
            ("Mountain Time", "Mountain Daylight Time", True),
            ("Central Daylight Time", "Mountain Daylight Time", False),
            # Superset match
            ("Central Standard Time", "Central", True),
            ("Civil War", "War", False),
            # Stop words
            ("The Beatles", "Beatles", True),
            ("A Tale of Two Cities", "Tale Two Cities", True),
            ("Virginia", "West Virginia", False),
            ("Dr.", "Dr. No", False),
            ("carnivore", "carnivorous", True),
            ("React", "Reaction", True),
            ("tape", "a stapler", False),
        ]
        for guess, answer, expected in cases:
            with self.subTest(guess=guess, answer=answer):
                result = self.checker.is_correct(guess, answer)
                self.assertEqual(
                    result, expected, f"Failed for guess='{guess}', answer='{answer}'"
                )


if __name__ == "__main__":
    unittest.main()
