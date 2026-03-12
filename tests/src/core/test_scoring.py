import unittest
from unittest.mock import MagicMock
from src.core.scoring import ScoreCalculator


class TestScoreCalculator(unittest.TestCase):
    def setUp(self):
        self.config = MagicMock()

        # Default side effects matching standard config
        def config_side_effect(key, default=None):
            if key == "JBOT_BONUS_TRY_CSV":
                return "20,10,5"
            if key == "JBOT_BONUS_FASTEST_CSV":
                return "10,5,5"
            if key == "JBOT_BONUS_BEFORE_HINT":
                return 10
            if key == "JBOT_BONUS_STREAK_PER_DAY":
                return 5
            if key == "JBOT_BONUS_STREAK_CAP":
                return 25

            # Emoji defaults
            if key == "JBOT_EMOJI_FIRST_TRY":
                return "🎯"
            if key == "JBOT_EMOJI_BEFORE_HINT":
                return "🧠"
            if key == "JBOT_EMOJI_FASTEST":
                return "🥇"
            if key == "JBOT_EMOJI_FASTEST_CSV":
                return "🥇,🥈,🥉"
            if key == "JBOT_EMOJI_STREAK":
                return "🔥"

            return default

        self.config.get.side_effect = config_side_effect
        self.calculator = ScoreCalculator(self.config)

    def test_base_points_only(self):
        # guesses_count=4 to ensure no try bonus
        points, bonuses, msgs = self.calculator.calculate_points(
            question_value=100,
            guesses_count=4,
            is_before_hint=False,
            answer_rank=0,
        )
        self.assertEqual(points, 100)
        self.assertEqual(bonuses, {})
        self.assertEqual(msgs, [])

    def test_first_try_bonus(self):
        points, bonuses, msgs = self.calculator.calculate_points(
            question_value=100,
            guesses_count=1,
            is_before_hint=False,
            answer_rank=0,
        )
        self.assertEqual(points, 120)
        self.assertEqual(bonuses["try_1"], 20)
        self.assertTrue(any("First try" in m for m in msgs))

    def test_second_try_bonus(self):
        points, bonuses, msgs = self.calculator.calculate_points(
            question_value=100,
            guesses_count=2,
            is_before_hint=False,
            answer_rank=0,
        )
        self.assertEqual(points, 110)  # 100 + 10
        self.assertEqual(bonuses["try_2"], 10)
        self.assertTrue(any("Try #2" in m for m in msgs))

    def test_third_try_bonus(self):
        points, bonuses, msgs = self.calculator.calculate_points(
            question_value=100,
            guesses_count=3,
            is_before_hint=False,
            answer_rank=0,
        )
        self.assertEqual(points, 105)  # 100 + 5
        self.assertEqual(bonuses["try_3"], 5)
        self.assertTrue(any("Try #3" in m for m in msgs))

    def test_before_hint_bonus(self):
        points, bonuses, msgs = self.calculator.calculate_points(
            question_value=100,
            guesses_count=4,
            is_before_hint=True,
            answer_rank=0,
        )
        self.assertEqual(points, 110)
        self.assertEqual(bonuses["before_hint"], 10)
        self.assertTrue(any("Pre-hint" in m for m in msgs))

    def test_fastest_bonus(self):
        points, bonuses, msgs = self.calculator.calculate_points(
            question_value=100,
            guesses_count=4,
            is_before_hint=False,
            answer_rank=1,
        )
        self.assertEqual(points, 110)
        self.assertEqual(bonuses["fastest_1"], 10)
        self.assertTrue(any("Fastest" in m for m in msgs))

    def test_second_fastest_bonus(self):
        points, bonuses, msgs = self.calculator.calculate_points(
            question_value=100,
            guesses_count=4,
            is_before_hint=False,
            answer_rank=2,
        )
        self.assertEqual(points, 105)  # 100 + 5
        self.assertEqual(bonuses["fastest_2"], 5)
        self.assertTrue(any("2nd Fastest" in m for m in msgs))

    def test_streak_bonus(self):
        # Streak 1: No bonus
        points, bonuses, _ = self.calculator.calculate_points(
            question_value=100,
            guesses_count=4,
            is_before_hint=False,
            answer_rank=0,
            streak_length=1,
        )
        self.assertEqual(points, 100)
        self.assertNotIn("streak", bonuses)

        # Streak 2: 10 points
        points, bonuses, msgs = self.calculator.calculate_points(
            question_value=100,
            guesses_count=4,
            is_before_hint=False,
            answer_rank=0,
            streak_length=2,
        )
        self.assertEqual(points, 110)  # 100 + 2*5
        self.assertEqual(bonuses["streak"], 10)
        self.assertTrue(any("streak" in m for m in msgs))

        # Streak Cap (e.g. 10 * 5 = 50 > 25 cap)
        points, bonuses, msgs = self.calculator.calculate_points(
            question_value=100,
            guesses_count=4,
            is_before_hint=False,
            answer_rank=0,
            streak_length=10,
        )
        self.assertEqual(points, 125)  # 100 + 25
        self.assertEqual(bonuses["streak"], 25)

    def test_all_bonuses(self):
        points, bonuses, _ = self.calculator.calculate_points(
            question_value=100,
            guesses_count=1,
            is_before_hint=True,
            answer_rank=1,
            streak_length=3,
        )
        # 100 + 20 (Try 1) + 10 (Hint) + 10 (Fastest 1) + 15 (Streak 3*5) = 155
        self.assertEqual(points, 155)
        # Expected keys: try_1, first_try, before_hint, fastest_1, fastest, streak
        self.assertEqual(len(bonuses), 6)

    def test_stealable_amount(self):
        bonuses = {
            "try_1": 20,
            "first_try": 20,
            "fastest_1": 10,
            "fastest": 10,
            "before_hint": 10,
        }
        stealable = self.calculator.get_stealable_amount(bonuses)
        # All bonuses stealable except streak; alias keys (first_try, fastest) excluded
        # to avoid double-counting: try_1 (20) + fastest_1 (10) + before_hint (10) = 40
        self.assertEqual(stealable, 40)

    def test_stealable_legacy(self):
        bonuses = {"first_place": 10}
        stealable = self.calculator.get_stealable_amount(bonuses)
        self.assertEqual(stealable, 10)
