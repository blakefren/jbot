"""Unit tests for shared live/replay game-event transitions."""

import unittest

from src.core.events import PowerUpEvent
from src.core.game_event_service import GameEventService
from tests.src.core._powerup_helpers import make_config


class TestGameEventService(unittest.TestCase):
    def setUp(self):
        self.service = GameEventService(make_config(steal_cost=2, retro_steal_cost=4))
        self.daily_state = {}

    def test_wrong_jinxed_guess_returns_persistable_penalty(self):
        self.service.process_powerup(
            self.daily_state,
            PowerUpEvent(None, "attacker", "jinx", "target"),
        )

        transition = self.service.process_guess(
            self.daily_state, "target", is_correct=False
        )

        self.assertEqual(transition.jinx_attacker_id, "attacker")
        self.assertEqual(transition.jinx_wrong_guess_penalty, 5)
        self.assertEqual(self.daily_state["attacker"].score_earned, -5)

    def test_correct_jinxed_guess_applies_rest_before_transfer(self):
        self.service.process_powerup(
            self.daily_state,
            PowerUpEvent(None, "attacker", "jinx", "target"),
        )

        transition = self.service.process_guess(
            self.daily_state,
            "target",
            is_correct=True,
            points_earned=100,
            bonuses={},
            pending_rest_multiplier=0.2,
        )

        self.assertEqual(transition.rest_bonus, 20)
        self.assertEqual(transition.jinx_transfer, 30)
        self.assertEqual(transition.points_earned, 90)
        self.assertEqual(self.daily_state["target"].score_earned, 90)
        self.assertEqual(self.daily_state["attacker"].score_earned, 30)

    def test_qualifying_correct_guess_consumes_pending_rest_multiplier(self):
        transition = self.service.process_guess(
            self.daily_state,
            "player",
            is_correct=True,
            points_earned=1,
            bonuses={},
            pending_rest_multiplier=0.2,
        )

        self.assertTrue(transition.consume_pending_rest_multiplier)
        self.assertEqual(transition.rest_bonus, 0)

    def test_wrong_guess_does_not_consume_pending_rest_multiplier(self):
        transition = self.service.process_guess(
            self.daily_state,
            "player",
            is_correct=False,
            pending_rest_multiplier=0.2,
        )

        self.assertFalse(transition.consume_pending_rest_multiplier)

    def test_forward_steal_returns_persistable_transfer(self):
        self.service.process_powerup(
            self.daily_state,
            PowerUpEvent(None, "thief", "steal", "target"),
            initial_streak=2,
        )

        transition = self.service.process_guess(
            self.daily_state,
            "target",
            is_correct=True,
            points_earned=130,
            bonuses={"try_1": 20, "before_hint": 10},
        )

        self.assertEqual(transition.steal_thief_id, "thief")
        self.assertEqual(transition.steal_transfer, 30)
        self.assertEqual(transition.points_earned, 100)
        self.assertEqual(self.daily_state["thief"].score_earned, 30)

    def test_retroactive_jinx_returns_transfer_and_prior_penalty(self):
        self.service.process_guess(self.daily_state, "target", is_correct=False)
        self.service.process_guess(
            self.daily_state,
            "target",
            is_correct=True,
            points_earned=100,
            bonuses={},
        )

        transition = self.service.process_powerup(
            self.daily_state,
            PowerUpEvent(None, "attacker", "jinx", "target"),
        )

        self.assertEqual(transition.jinx_transfer, 25)
        self.assertEqual(transition.jinx_wrong_guess_penalty, 5)
        self.assertEqual(self.daily_state["attacker"].score_earned, 20)

    def test_retaliatory_powerup_is_rejected_without_state_mutation(self):
        self.service.process_powerup(
            self.daily_state,
            PowerUpEvent(None, "first", "jinx", "second"),
        )

        transition = self.service.process_powerup(
            self.daily_state,
            PowerUpEvent(None, "second", "steal", "first"),
            initial_streak=2,
        )

        self.assertEqual(transition.rejection_reason, "retaliation_blocked")
        self.assertIsNone(self.daily_state["second"].stealing_from)
        self.assertIsNone(self.daily_state["first"].steal_attempt_by)


if __name__ == "__main__":
    unittest.main()
