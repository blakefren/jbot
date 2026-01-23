import unittest
from unittest.mock import MagicMock
from src.core.scoring import ScoreCalculator


class TestScoreCalculatorCSV(unittest.TestCase):
    def setUp(self):
        self.config = MagicMock()

    def test_extended_try_messaging(self):
        # Configure 5 tiers of try bonuses
        self.config.get.side_effect = lambda k, d=None: (
            "20,10,5,2,1" if k == "JBOT_BONUS_TRY_CSV" else d
        )
        calculator = ScoreCalculator(self.config)

        # Test 4th Try
        points, bonuses, msgs = calculator.calculate_points(
            question_value=100, guesses_count=4, is_before_hint=False, answer_rank=0
        )
        self.assertEqual(points, 102)  # 100 + 2
        self.assertEqual(bonuses["try_4"], 2)
        self.assertTrue(any("Try #4" in m for m in msgs))

        # Test 5th Try
        points, bonuses, msgs = calculator.calculate_points(
            question_value=100, guesses_count=5, is_before_hint=False, answer_rank=0
        )
        self.assertEqual(points, 101)  # 100 + 1
        self.assertTrue(any("Try #5" in m for m in msgs))

    def test_extended_fastest_messaging(self):
        # Configure 4 tiers of fastest bonuses
        self.config.get.side_effect = lambda k, d=None: (
            "10,5,5,1" if k == "JBOT_BONUS_FASTEST_CSV" else d
        )
        calculator = ScoreCalculator(self.config)

        # Test 4th Fastest
        points, bonuses, msgs = calculator.calculate_points(
            question_value=100,
            guesses_count=4,  # No try bonus
            is_before_hint=False,
            answer_rank=4,
        )
        self.assertEqual(points, 101)  # 100 + 1
        self.assertEqual(bonuses["fastest_4"], 1)
        self.assertTrue(any("4th Fastest" in m for m in msgs))

    def test_csv_parsing_whitespace(self):
        # Test spaces in CSV
        self.config.get.side_effect = lambda k, d=None: (
            " 20 , 10 , 5 " if k == "JBOT_BONUS_TRY_CSV" else d
        )
        calculator = ScoreCalculator(self.config)
        self.assertEqual(calculator.bonus_try_list, [20, 10, 5])

    def test_csv_parsing_invalid(self):
        # Test invalid content falls back to default
        # Default for TRY is "20,10,5" -> [20, 10, 5]
        def side_effect(key, default=None):
            if key == "JBOT_BONUS_TRY_CSV":
                return "20,abc,5"
            return default  # Return the provided default for other keys

        self.config.get.side_effect = side_effect
        calculator = ScoreCalculator(self.config)
        self.assertEqual(calculator.bonus_try_list, [20, 10, 5])

    def test_csv_parsing_empty(self):
        # Test empty string results in empty list
        self.config.get.side_effect = lambda k, d=None: (
            "" if k == "JBOT_BONUS_TRY_CSV" else d
        )
        calculator = ScoreCalculator(self.config)
        self.assertEqual(calculator.bonus_try_list, [])

        # Ensure no bonuses awarded
        points, bonuses, _ = calculator.calculate_points(
            question_value=100, guesses_count=1, is_before_hint=False, answer_rank=0
        )
        self.assertEqual(points, 100)
        self.assertNotIn("try_1", bonuses)

    def test_stealable_amount_dynamic(self):
        # Setup calculator with defaults
        self.config.get.side_effect = lambda k, d=None: d
        calculator = ScoreCalculator(self.config)

        # Simulate bonuses dict that would be generated
        # e.g. Rank 4 (1pt), Try 4 (2pts)
        bonuses = {"fastest_4": 1, "try_4": 2, "streak": 5}

        stealable = calculator.get_stealable_amount(bonuses)
        # Should sum fastest_4 + try_4 = 3
        self.assertEqual(stealable, 3)

    def test_extended_fastest_emojis(self):
        # Configure emojis
        def side_effect(key, default=None):
            if key == "JBOT_BONUS_FASTEST_CSV":
                return "10,5,5,1"
            if key == "JBOT_EMOJI_FASTEST_CSV":
                return "🥇,🥈,🥉,🏅"
            return default

        self.config.get.side_effect = side_effect
        calculator = ScoreCalculator(self.config)

        # Test 2nd Fastest
        _, _, msgs = calculator.calculate_points(
            question_value=100, guesses_count=4, is_before_hint=False, answer_rank=2
        )
        self.assertTrue(any("🥈 2nd Fastest" in m for m in msgs))

        # Test 4th Fastest
        _, _, msgs = calculator.calculate_points(
            question_value=100, guesses_count=4, is_before_hint=False, answer_rank=4
        )
        self.assertTrue(any("🏅 4th Fastest" in m for m in msgs))
