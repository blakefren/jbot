import unittest
from unittest.mock import MagicMock
from src.core.scoring import ScoreCalculator


class TestScoreCalculator(unittest.TestCase):
    def setUp(self):
        self.config = MagicMock()

        # Default side effects matching standard config
        def config_side_effect(key, default=None):
            if key == "JBOT_BONUS_FIRST_TRY":
                return 20
            if key == "JBOT_BONUS_BEFORE_HINT":
                return 10
            if key == "JBOT_BONUS_FASTEST":
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
            if key == "JBOT_EMOJI_STREAK":
                return "🔥"

            return default

        self.config.get.side_effect = config_side_effect
        self.calculator = ScoreCalculator(self.config)

    def test_base_points_only(self):
        points, bonuses, msgs = self.calculator.calculate_points(
            question_value=100,
            is_first_try=False,
            is_before_hint=False,
            is_fastest=False,
        )
        self.assertEqual(points, 100)
        self.assertEqual(bonuses, {})
        self.assertEqual(msgs, [])

    def test_first_try_bonus(self):
        points, bonuses, msgs = self.calculator.calculate_points(
            question_value=100,
            is_first_try=True,
            is_before_hint=False,
            is_fastest=False,
        )
        self.assertEqual(points, 120)
        self.assertEqual(bonuses["first_try"], 20)
        self.assertTrue(any("First try" in m for m in msgs))

    def test_before_hint_bonus(self):
        points, bonuses, msgs = self.calculator.calculate_points(
            question_value=100,
            is_first_try=False,
            is_before_hint=True,
            is_fastest=False,
        )
        self.assertEqual(points, 110)
        self.assertEqual(bonuses["before_hint"], 10)
        self.assertTrue(any("Pre-hint" in m for m in msgs))

    def test_fastest_bonus(self):
        points, bonuses, msgs = self.calculator.calculate_points(
            question_value=100,
            is_first_try=False,
            is_before_hint=False,
            is_fastest=True,
        )
        self.assertEqual(points, 110)
        self.assertEqual(bonuses["fastest"], 10)
        self.assertTrue(any("Fastest" in m for m in msgs))

    def test_streak_bonus(self):
        # Streak 1: No bonus
        points, bonuses, _ = self.calculator.calculate_points(
            question_value=100,
            is_first_try=False,
            is_before_hint=False,
            is_fastest=False,
            streak_length=1,
        )
        self.assertEqual(points, 100)
        self.assertNotIn("streak", bonuses)

        # Streak 2: 10 points
        points, bonuses, msgs = self.calculator.calculate_points(
            question_value=100,
            is_first_try=False,
            is_before_hint=False,
            is_fastest=False,
            streak_length=2,
        )
        self.assertEqual(points, 110)  # 100 + 2*5
        self.assertEqual(bonuses["streak"], 10)
        self.assertTrue(any("streak" in m for m in msgs))

        # Streak Cap (e.g. 10 * 5 = 50 > 25 cap)
        points, bonuses, msgs = self.calculator.calculate_points(
            question_value=100,
            is_first_try=False,
            is_before_hint=False,
            is_fastest=False,
            streak_length=10,
        )
        self.assertEqual(points, 125)  # 100 + 25
        self.assertEqual(bonuses["streak"], 25)

    def test_all_bonuses(self):
        points, bonuses, _ = self.calculator.calculate_points(
            question_value=100,
            is_first_try=True,
            is_before_hint=True,
            is_fastest=True,
            streak_length=3,
        )
        # 100 + 20 + 10 + 10 + 15 = 155
        self.assertEqual(points, 155)
        self.assertEqual(len(bonuses), 4)

    def test_stealable_amount(self):
        bonuses = {"first_try": 20, "fastest": 10, "before_hint": 10}
        stealable = self.calculator.get_stealable_amount(bonuses)
        # Stealable: First Try + Fastest = 30. Pre-hint not stealable.
        self.assertEqual(stealable, 30)

    def test_stealable_legacy(self):
        bonuses = {"first_place": 10}
        stealable = self.calculator.get_stealable_amount(bonuses)
        self.assertEqual(stealable, 10)
