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
            vals = {
                "JBOT_BONUS_TRY_CSV": "20,10,5",
                "JBOT_BONUS_FASTEST_CSV": "10,5,5",
                "JBOT_BONUS_BEFORE_HINT": 10,
                "JBOT_BONUS_STREAK_PER_DAY": 5,
                "JBOT_BONUS_STREAK_CAP": 25,
                "JBOT_EMOJI_FIRST_TRY": "🎯",
                "JBOT_EMOJI_BEFORE_HINT": "🧠",
                "JBOT_EMOJI_FASTEST": "🥇",
                "JBOT_EMOJI_FASTEST_CSV": "🥇,🥈,🥉",
                "JBOT_EMOJI_STREAK": "🔥",
                "JBOT_REINFORCE_COST": 25,
                "JBOT_EMOJI_JINXED": "🥶",
                "JBOT_EMOJI_SILENCED": "🤐",
                "JBOT_EMOJI_STOLEN_FROM": "💸",
                "JBOT_EMOJI_STEALING": "💰",
                "JBOT_EMOJI_REST": "😴",
            }
            return vals.get(key, default)

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
        # Streak: 3 * 5 = 15 (Initial 2 + 1 = 3)
        # Total: 155
        self.assertEqual(results["p1"]["score_earned"], 155)
        self.assertEqual(results["p1"]["streak_delta"], 1)
        self.assertEqual(results["p1"]["final_score"], 255)
        self.assertEqual(results["p1"]["final_streak"], 3)

        # P2: Incorrect. 0 points.
        self.assertEqual(results["p2"]["score_earned"], 0)
        self.assertEqual(results["p2"]["streak_delta"], 0)

        # P3: Did not answer. Streak reset.
        self.assertEqual(results["p3"]["score_earned"], 0)
        self.assertEqual(results["p3"]["streak_delta"], -5)
        self.assertEqual(results["p3"]["final_streak"], 0)

    def test_rest_mechanic(self):
        """A resting player earns 0 points and has their streak frozen."""
        events = [
            PowerUpEvent(
                timestamp="2023-01-01 09:00:00",
                user_id="p1",
                powerup_type="rest",
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

        # Player rested: 0 points, streak unchanged (delta = 0)
        self.assertEqual(results["p1"]["score_earned"], 0)
        self.assertEqual(results["p1"]["streak_delta"], 0)
        self.assertEqual(results["p1"]["final_streak"], 2)  # unchanged

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

        # P1 answers second (1st try for P1, 2nd fastest overall).
        # P1 effective streak after -2 cost: max(0, 2-2) = 0 → streak_length=1 (<2, no streak bonus)
        # P1 Bonuses: Try 1 (20), Fastest 2 (5), Before Hint (10).
        # Total P1 Score: 100 + 20 + 5 + 10 = 135.

        # Steal Logic (partial steal: P1 streak=2, cost=3 → ratio=2/3):
        # Stealable bonuses (all except streak; aliases skipped when canonical present):
        # try_1 (20) + fastest_1 (10) + before_hint (10) = 40.
        # Stolen = round(40 * 2/3) = 27.
        # P3 loses 27 -> 138.
        # P1 gains 27 -> 162.

        simulator = DailyGameSimulator(
            self.question,
            self.answers,
            self.hint_timestamp,
            events,
            self.initial_states,
            self.config,
        )
        results = simulator.run()

        self.assertEqual(results["p3"]["score_earned"], 138)
        self.assertEqual(results["p1"]["score_earned"], 162)

        # P1 streak cost: deducted=min(3,2)=2, handle_guess +1 → net -1
        self.assertEqual(results["p1"]["streak_delta"], -1)
