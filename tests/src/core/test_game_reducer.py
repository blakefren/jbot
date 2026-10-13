"""Differential tests for the copy-on-write Phase 3 reducer foundation."""

from copy import deepcopy
import unittest

from src.core.events import PowerUpEvent
from src.core.game_event_service import GameEventService
from src.core.game_reducer import DailyGameReducer
from src.core.state import DailyPlayerState
from tests.src.core._powerup_helpers import make_config


class TestDailyGameReducer(unittest.TestCase):
    def setUp(self):
        config = make_config(steal_cost=2, retro_steal_cost=4)
        self.service = GameEventService(config)
        self.reducer = DailyGameReducer(config)

    def test_reduce_guess_matches_service_without_mutating_input(self):
        daily_state = {}
        self.service.process_powerup(
            daily_state,
            PowerUpEvent(None, "attacker", "jinx", "target"),
        )
        original_state = deepcopy(daily_state)
        service_state = deepcopy(daily_state)

        expected = self.service.process_guess(
            service_state,
            "target",
            is_correct=True,
            points_earned=100,
            bonuses={},
            pending_rest_multiplier=0.2,
        )
        result = self.reducer.reduce_guess(
            daily_state,
            "target",
            is_correct=True,
            points_earned=100,
            bonuses={},
            pending_rest_multiplier=0.2,
        )

        self.assertEqual(daily_state, original_state)
        self.assertEqual(result.daily_state, service_state)
        self.assertEqual(result.transition, expected)

    def test_reduce_guess_prelude_matches_service_for_all_guard_outcomes(self):
        cases = (
            ("new-player", {}, False),
            (
                "already-correct",
                {"player": DailyPlayerState(is_correct=True, guesses_count=2)},
                True,
            ),
            (
                "resting",
                {"player": DailyPlayerState(is_resting=True, guesses_count=2)},
                True,
            ),
        )
        for name, daily_state, is_correct in cases:
            with self.subTest(name=name):
                original_state = deepcopy(daily_state)
                service_state = deepcopy(daily_state)

                expected = self.service.process_guess(
                    service_state,
                    "player",
                    is_correct=is_correct,
                    points_earned=100,
                    bonuses={},
                )
                result = self.reducer.reduce_guess(
                    daily_state,
                    "player",
                    is_correct=is_correct,
                    points_earned=100,
                    bonuses={},
                )

                self.assertEqual(daily_state, original_state)
                self.assertEqual(result.daily_state, service_state)
                self.assertEqual(result.transition, expected)

    def test_reduce_powerup_matches_service_without_mutating_input(self):
        daily_state = {}
        self.service.process_powerup(
            daily_state,
            PowerUpEvent(None, "first", "jinx", "second"),
        )
        original_state = deepcopy(daily_state)
        service_state = deepcopy(daily_state)
        event = PowerUpEvent(None, "second", "steal", "first")

        expected = self.service.process_powerup(service_state, event, initial_streak=2)
        result = self.reducer.reduce_powerup(daily_state, event, initial_streak=2)

        self.assertEqual(daily_state, original_state)
        self.assertEqual(result.daily_state, service_state)
        self.assertEqual(result.transition, expected)


if __name__ == "__main__":
    unittest.main()
