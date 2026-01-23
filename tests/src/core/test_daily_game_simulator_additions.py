import unittest
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
                "JBOT_EMOJI_SHIELD": "💝",
                "JBOT_EMOJI_SHIELD_BROKEN": "💔",
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
        # P1 uses shield but doesn"t use it (should decay if end of day)
        # P3 doesn"t answer (should reset streak if end of day)
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

        # Run WITHOUT end of day logic
        results = simulator.run(apply_end_of_day=False)

        # P1: Shield active, no decay (-10)
        self.assertEqual(results["p1"]["score_earned"], 0)
        self.assertTrue(simulator.daily_state["p1"].shield_active)

        # P3: No answer, no streak reset (and thus not in results because apply_end_of_day=False)
        self.assertNotIn("p3", results)

    def test_wager_win(self):
        """Test wager logic: deduction and win multiplier."""
        events = [
            PowerUpEvent(
                timestamp="2023-01-01 09:00:00",
                user_id="p1",
                powerup_type="wager",
                amount=50,
            ),
            GuessEvent(
                timestamp="2023-01-01 10:00:00",
                user_id="p1",
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

        # P1 Score Calculation:
        # Initial: 100
        # Wager: -50 (Current: 50)
        # Correct Answer Points:
        #   Base: 100
        #   First Try: 20
        #   Before Hint: 10
        #   Fastest: 10
        #   Streak: 3*5 = 15
        #   Total Earned: 155
        # Score before wager resolution: 50 + 155 = 205 ? NO. Wager calc uses pre-points score.
        # Wager Winnings: 50 * (100 / (50 + 100)) = 33
        # Total Score Earned: 155 + 33 = 188

        self.assertEqual(results["p1"]["score_earned"], 188)

    def test_wager_loss(self):
        """Test wager logic: deduction and loss."""
        events = [
            PowerUpEvent(
                timestamp="2023-01-01 09:00:00",
                user_id="p1",
                powerup_type="wager",
                amount=50,
            ),
            GuessEvent(
                timestamp="2023-01-01 10:00:00",
                user_id="p1",
                guess_text="wrong",
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

        # P1 Score: -50 (Wager lost)
        self.assertEqual(results["p1"]["score_earned"], -50)

    def test_teamup(self):
        """Test teamup logic."""
        events = [
            PowerUpEvent(
                timestamp="2023-01-01 09:00:00",
                user_id="p1",
                powerup_type="teamup",
                target_user_id="p2",
            ),
            GuessEvent(
                timestamp="2023-01-01 10:00:00",
                user_id="p1",
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

        # P1:
        # Cost: -25
        # Answer: Correct (points earned, let"s say 100 base)
        # Team Success: True

        # P2:
        # Cost: -25
        # Team Success: True (via P1)

        self.assertTrue(simulator.daily_state["p1"].team_success)
        self.assertTrue(simulator.daily_state["p2"].team_success)
        self.assertEqual(simulator.daily_state["p1"].team_partner, "p2")
        self.assertEqual(simulator.daily_state["p2"].team_partner, "p1")
