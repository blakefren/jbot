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
        self.assertTrue(simulator.daily_state["p1"]["shield_active"])

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
        #   Streak: 2*5 = 10
        #   Total Earned: 150
        # Score before wager resolution: 50 + 150 = 200
        # Wager Winnings: 50 * (100 / (50 + 100)) = 33
        # Total Score Earned: 150 + 33 = 183

        self.assertEqual(results["p1"]["score_earned"], 183)

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

        # Mock config for teamup cost
        self.config.get.side_effect = lambda k, d=None: (
            25 if k == "JBOT_REINFORCE_COST" else d
        )

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

        self.assertTrue(simulator.daily_state["p1"]["team_success"])
        self.assertTrue(simulator.daily_state["p2"]["team_success"])
        self.assertEqual(simulator.daily_state["p1"]["team_partner"], "p2")
        self.assertEqual(simulator.daily_state["p2"]["team_partner"], "p1")
