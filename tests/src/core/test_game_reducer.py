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

    def _assert_guess_matches_service(
        self,
        daily_state: dict[str, DailyPlayerState],
        player_id: str,
        **kwargs,
    ) -> dict[str, DailyPlayerState]:
        original_state = deepcopy(daily_state)
        service_state = deepcopy(daily_state)

        expected = self.service.process_guess(
            service_state, player_id, **deepcopy(kwargs)
        )
        result = self.reducer.reduce_guess(daily_state, player_id, **deepcopy(kwargs))

        self.assertEqual(daily_state, original_state)
        self.assertEqual(result.daily_state, service_state)
        self.assertEqual(result.transition, expected)
        return result.daily_state

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

    def test_reduce_guess_matches_service_for_wrong_jinxed_guess(self):
        daily_state = {}
        self.service.process_powerup(
            daily_state,
            PowerUpEvent(None, "attacker", "jinx", "target"),
        )
        original_state = deepcopy(daily_state)
        service_state = deepcopy(daily_state)

        expected = self.service.process_guess(service_state, "target", is_correct=False)
        result = self.reducer.reduce_guess(daily_state, "target", is_correct=False)

        self.assertEqual(daily_state, original_state)
        self.assertEqual(result.daily_state, service_state)
        self.assertEqual(result.transition, expected)

    def test_reduce_guess_matches_service_for_multiple_wrong_jinxed_guesses(self):
        service_state = {}
        reducer_state = {}
        jinx = PowerUpEvent(None, "attacker", "jinx", "target")
        self.service.process_powerup(service_state, jinx)
        self.service.process_powerup(reducer_state, jinx)

        for is_correct in (False, False, True):
            expected = self.service.process_guess(
                service_state,
                "target",
                is_correct=is_correct,
                points_earned=100 if is_correct else 0,
                bonuses={} if is_correct else None,
            )
            original_state = deepcopy(reducer_state)
            result = self.reducer.reduce_guess(
                reducer_state,
                "target",
                is_correct=is_correct,
                points_earned=100 if is_correct else 0,
                bonuses={} if is_correct else None,
            )

            self.assertEqual(reducer_state, original_state)
            self.assertEqual(result.daily_state, service_state)
            self.assertEqual(result.transition, expected)
            reducer_state = result.daily_state

        self.assertEqual(service_state["attacker"].jinx_penalty_total, 10)

    def test_reduce_guess_matches_service_for_forward_steal(self):
        daily_state = {}
        self.service.process_powerup(
            daily_state,
            PowerUpEvent(None, "thief", "steal", "target"),
            initial_streak=2,
        )
        original_state = deepcopy(daily_state)
        service_state = deepcopy(daily_state)

        expected = self.service.process_guess(
            service_state,
            "target",
            is_correct=True,
            points_earned=130,
            bonuses={"try_1": 20, "before_hint": 10},
        )
        result = self.reducer.reduce_guess(
            daily_state,
            "target",
            is_correct=True,
            points_earned=130,
            bonuses={"try_1": 20, "before_hint": 10},
        )

        self.assertEqual(daily_state, original_state)
        self.assertEqual(result.daily_state, service_state)
        self.assertEqual(result.transition, expected)

    def test_reduce_guess_matches_service_for_partial_forward_steal(self):
        daily_state = {}
        self.service.process_powerup(
            daily_state,
            PowerUpEvent(None, "thief", "steal", "target"),
            initial_streak=1,
        )

        result_state = self._assert_guess_matches_service(
            daily_state,
            "target",
            is_correct=True,
            points_earned=130,
            bonuses={"try_1": 20, "before_hint": 10},
        )

        self.assertEqual(result_state["thief"].steal_ratio, 0.5)
        self.assertEqual(result_state["thief"].score_earned, 15)

    def test_reduce_guess_matches_service_for_no_stealable_bonuses(self):
        daily_state = {}
        self.service.process_powerup(
            daily_state,
            PowerUpEvent(None, "thief", "steal", "target"),
            initial_streak=2,
        )

        result_state = self._assert_guess_matches_service(
            daily_state,
            "target",
            is_correct=True,
            points_earned=120,
            bonuses={"streak": 20},
        )

        self.assertEqual(result_state["thief"].score_earned, 0)

    def test_reduce_guess_matches_service_for_jinx_and_steal_ordering(self):
        daily_state = {}
        self.service.process_powerup(
            daily_state,
            PowerUpEvent(None, "jinxer", "jinx", "target"),
        )
        self.service.process_powerup(
            daily_state,
            PowerUpEvent(None, "thief", "steal", "target"),
            initial_streak=2,
        )

        result_state = self._assert_guess_matches_service(
            daily_state,
            "target",
            is_correct=True,
            points_earned=130,
            bonuses={"try_1": 20, "before_hint": 10},
            pending_rest_multiplier=0.2,
        )

        self.assertEqual(result_state["jinxer"].score_earned, 39)
        self.assertEqual(result_state["thief"].score_earned, 30)
        self.assertEqual(result_state["target"].score_earned, 87)

    def test_reduce_guess_jinx_excludes_previously_stolen_points(self):
        daily_state = {
            "target": DailyPlayerState(score_stolen=40, jinxed_by="attacker"),
            "attacker": DailyPlayerState(jinx_target="target"),
        }

        result_state = self._assert_guess_matches_service(
            daily_state,
            "target",
            is_correct=True,
            points_earned=100,
            bonuses={},
        )

        self.assertEqual(result_state["attacker"].score_earned, 15)

    def test_reduce_guess_consumes_rounded_zero_rest_bonus(self):
        result_state = self._assert_guess_matches_service(
            {},
            "player",
            is_correct=True,
            points_earned=1,
            bonuses={},
            pending_rest_multiplier=0.2,
        )

        self.assertEqual(result_state["player"].score_earned, 1)

    def test_reduce_guess_blocks_duplicate_jinx_resolution(self):
        service_state = {}
        reducer_state = {}
        jinx = PowerUpEvent(None, "attacker", "jinx", "target")
        self.service.process_powerup(service_state, jinx)
        self.service.process_powerup(reducer_state, jinx)

        for _ in range(2):
            expected = self.service.process_guess(
                service_state,
                "target",
                is_correct=True,
                points_earned=100,
                bonuses={},
            )
            original_state = deepcopy(reducer_state)
            result = self.reducer.reduce_guess(
                reducer_state,
                "target",
                is_correct=True,
                points_earned=100,
                bonuses={},
            )

            self.assertEqual(reducer_state, original_state)
            self.assertEqual(result.daily_state, service_state)
            self.assertEqual(result.transition, expected)
            reducer_state = result.daily_state

        self.assertEqual(service_state["attacker"].score_earned, 25)

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
