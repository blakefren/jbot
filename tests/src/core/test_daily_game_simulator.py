import unittest
from unittest.mock import MagicMock
from src.core.daily_game_simulator import DailyGameSimulator
from src.core.events import GuessEvent, PowerUpEvent
from src.core.player import Player
from data.readers.question import Question


class TestDailyGameSimulator(unittest.TestCase):
    def setUp(self):
        self.question = Question(
            question="What is 2+2?", answer="4", category="Math", clue_value=100
        )
        self.answers = ["4", "four"]
        self.hint_timestamp = "2023-01-01 12:00:00"
        self.config = MagicMock()

        # Common config side effect
        def config_side_effect(key, default=None):
            if key == "JBOT_BONUS_FIRST_TRY":
                return 20
            if key == "JBOT_BONUS_BEFORE_HINT":
                return 10
            if key == "JBOT_BONUS_FIRST_PLACE":
                return 10
            if key == "JBOT_BONUS_STREAK_PER_DAY":
                return 5
            if key == "JBOT_BONUS_STREAK_CAP":
                return 25
            return default

        self.config.get.side_effect = config_side_effect

        self.initial_states = {
            "p1": Player(id="p1", name="Player 1", score=100, answer_streak=2),
            "p2": Player(id="p2", name="Player 2", score=50, answer_streak=0),
            "p3": Player(id="p3", name="Player 3", score=200, answer_streak=5),
        }

    def test_basic_scoring(self):
        events = [
            GuessEvent(
                timestamp="2023-01-01 10:00:00",
                user_id="p1",
                guess_text="4",
                is_correct=True,
            ),
            GuessEvent(
                timestamp="2023-01-01 10:05:00",
                user_id="p2",
                guess_text="5",
                is_correct=False,
            ),
        ]

        simulator = DailyGameSimulator(
            self.question,
            self.answers,
            self.hint_timestamp,
            events,
            self.initial_states,
            self.config,
        )
        results = simulator.run()

        # P1: Correct.
        # Base: 100
        # First Try: 20
        # Before Hint: 10
        # Fastest: 10 (First correct)
        # Streak: 2 * 5 = 10
        # Total: 150
        self.assertEqual(results["p1"]["score_earned"], 150)
        self.assertEqual(results["p1"]["streak_delta"], 1)
        self.assertEqual(results["p1"]["final_score"], 250)
        self.assertEqual(results["p1"]["final_streak"], 3)

        # P2: Incorrect. 0 points.
        self.assertEqual(results["p2"]["score_earned"], 0)
        self.assertEqual(results["p2"]["streak_delta"], 0)

        # P3: Did not answer. Streak reset.
        self.assertEqual(results["p3"]["score_earned"], 0)
        self.assertEqual(results["p3"]["streak_delta"], -5)
        self.assertEqual(results["p3"]["final_streak"], 0)

    def test_shield_usage(self):
        events = [
            PowerUpEvent(
                timestamp="2023-01-01 09:00:00",
                user_id="p1",
                powerup_type="shield",
                target_user_id=None,
            ),
        ]

        simulator = DailyGameSimulator(
            self.question,
            self.answers,
            self.hint_timestamp,
            events,
            self.initial_states,
            self.config,
        )
        results = simulator.run()

        self.assertEqual(results["p1"]["score_earned"], -10)

    def test_jinx_success(self):
        # Re-run with P3 as target
        events = [
            PowerUpEvent(
                timestamp="2023-01-01 09:00:00",
                user_id="p1",
                powerup_type="jinx",
                target_user_id="p3",
            ),
            GuessEvent(
                timestamp="2023-01-01 10:00:00",
                user_id="p3",
                guess_text="4",
                is_correct=True,
            ),
        ]
        simulator = DailyGameSimulator(
            self.question,
            self.answers,
            self.hint_timestamp,
            events,
            self.initial_states,
            self.config,
        )
        results = simulator.run()

        # P3 Streak bonus would be 5 * 5 = 25.
        # But jinxed -> 0.
        # Score: 100 + 20 + 10 + 10 = 140.
        self.assertEqual(results["p3"]["score_earned"], 140)
        self.assertNotIn("streak", results["p3"]["bonuses"])

    def test_steal_success(self):
        events = [
            PowerUpEvent(
                timestamp="2023-01-01 09:00:00",
                user_id="p1",
                powerup_type="steal",
                target_user_id="p3",
            ),
            GuessEvent(
                timestamp="2023-01-01 10:00:00",
                user_id="p3",
                guess_text="4",
                is_correct=True,
            ),
            GuessEvent(
                timestamp="2023-01-01 10:01:00",
                user_id="p1",
                guess_text="4",
                is_correct=True,
            ),
        ]

        # P3 answers first.
        # P3 Bonuses: First Try (20), Before Hint (10), Fastest (10), Streak (25).
        # Total P3 Score: 100 + 20 + 10 + 10 + 25 = 165.

        # P1 answers second.
        # P1 Bonuses: First Try (20), Before Hint (10), Streak (0 - reset by steal).
        # Total P1 Score: 100 + 20 + 10 + 0 = 130.

        # Steal Logic:
        # P1 steals from P3.
        # Stealable bonuses: "first_try" (20), "fastest" (10). Total 30.
        # P3 loses 30 -> 135.
        # P1 gains 30 -> 160.

        simulator = DailyGameSimulator(
            self.question,
            self.answers,
            self.hint_timestamp,
            events,
            self.initial_states,
            self.config,
        )
        results = simulator.run()

        self.assertEqual(results["p3"]["score_earned"], 135)
        self.assertEqual(results["p1"]["score_earned"], 160)

        # P1 streak reset cost?
        # handle_powerup for steal:
        # state["streak_delta"] = -initial_streak (-2)
        # handle_guess: +1
        # Net: -1
        self.assertEqual(results["p1"]["streak_delta"], -1)
