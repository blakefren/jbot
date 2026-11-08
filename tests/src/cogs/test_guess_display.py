import unittest

from src.core.guess_display import format_guesses, truncate_discord_text


class TestGuessDisplay(unittest.TestCase):
    def test_format_guesses(self):
        self.assertEqual(
            format_guesses(
                [
                    {"guess_text": "Banana"},
                    {"guess_text": "Apple"},
                    {"guess_text": "apple"},
                ]
            ),
            "1. apple\n2. banana",
        )
        self.assertEqual(format_guesses([]), "No guesses yet.")

    def test_truncate_at_discord_limits(self):
        for limit in (100, 2000):
            with self.subTest(limit=limit):
                self.assertEqual(truncate_discord_text("x" * limit, limit), "x" * limit)
                result = truncate_discord_text("x" * (limit + 1), limit)
                self.assertLessEqual(len(result), limit)
                self.assertTrue(result.endswith("\n... (truncated)"))

    def test_truncate_counts_astral_characters_conservatively(self):
        text = "\U0001f600" * 51
        result = truncate_discord_text(text, 100)
        self.assertLessEqual(len(result.encode("utf-16-le")) // 2, 100)
        self.assertTrue(result.endswith("\n... (truncated)"))
