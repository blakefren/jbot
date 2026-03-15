import unittest
from datetime import datetime
from unittest.mock import MagicMock
from src.core.daily_game_simulator import DailyGameSimulator
from src.core.events import GuessEvent, PowerUpEvent
from src.core.player import Player
from data.readers.question import Question


class TestDailyGameSimulatorAdditions(unittest.TestCase):
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

    def test_run_midday(self):
        """Test that run(apply_end_of_day=False) skips decay and resets."""
        # P1 uses rest (streak should be frozen, not reset)
        # P3 doesn"t answer (should reset streak if end of day)
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

        # Run WITHOUT end of day logic
        results = simulator.run(apply_end_of_day=False)

        # P1: Resting, 0 points, streak unchanged
        self.assertEqual(results["p1"]["score_earned"], 0)
        self.assertTrue(simulator.daily_state["p1"].is_resting)

        # P3: No answer, not in results when apply_end_of_day=False
        self.assertNotIn("p3", results)

    def test_sort_with_mixed_datetime_and_str_timestamps(self):
        """Regression: sorting events with mixed datetime/str timestamps must not raise TypeError."""
        events = [
            GuessEvent(
                timestamp=datetime(2023, 1, 1, 10, 5, 0),  # datetime object
                user_id="p2",
                guess_text="4",
            ),
            PowerUpEvent(
                timestamp="2023-01-01 09:00:00",  # str
                user_id="p1",
                powerup_type="rest",
                target_user_id=None,
            ),
            GuessEvent(
                timestamp=datetime(2023, 1, 1, 10, 0, 0),  # datetime object
                user_id="p1",
                guess_text="4",
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
        # Should not raise TypeError when sorting mixed timestamp types
        results = simulator.run()
        self.assertIn("p1", results)
        self.assertIn("p2", results)

    def test_hint_comparison_with_datetime_event_timestamp(self):
        """Regression: comparing a datetime event timestamp against a str hint_timestamp must not raise TypeError."""
        # Guess before hint (datetime ts < str hint_timestamp)
        events_before = [
            GuessEvent(
                timestamp=datetime(2023, 1, 1, 10, 0, 0),
                user_id="p1",
                guess_text="4",
            ),
        ]
        simulator = DailyGameSimulator(
            self.question,
            self.answers,
            "2023-01-01 12:00:00",  # str hint_timestamp
            events_before,
            self.initial_states,
            self.config,
        )
        results = simulator.run(apply_end_of_day=False)
        # Before-hint bonus should apply
        self.assertIn("🧠", results["p1"]["badges"])

        # Guess after hint (datetime ts > str hint_timestamp)
        events_after = [
            GuessEvent(
                timestamp=datetime(2023, 1, 1, 14, 0, 0),
                user_id="p1",
                guess_text="4",
            ),
        ]
        simulator2 = DailyGameSimulator(
            self.question,
            self.answers,
            "2023-01-01 12:00:00",  # str hint_timestamp
            events_after,
            self.initial_states,
            self.config,
        )
        results2 = simulator2.run(apply_end_of_day=False)
        # Before-hint bonus should NOT apply
        self.assertNotIn("🧠", results2["p1"]["badges"])

    def test_hint_timestamp_as_datetime_object(self):
        """hint_timestamp provided as a datetime object should work without TypeError."""
        events = [
            GuessEvent(
                timestamp="2023-01-01 10:00:00",
                user_id="p1",
                guess_text="4",
            ),
        ]
        simulator = DailyGameSimulator(
            self.question,
            self.answers,
            datetime(2023, 1, 1, 12, 0, 0),  # datetime object, not str
            events,
            self.initial_states,
            self.config,
        )
        # Should not raise TypeError
        results = simulator.run(apply_end_of_day=False)
        # Guess is before the datetime hint_timestamp, so before-hint bonus applies
        self.assertIn("🧠", results["p1"]["badges"])
