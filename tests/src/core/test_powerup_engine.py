"""
Unit tests for PowerUpEngine — pure state-mutation logic with no DB or Discord dependencies.

Each test builds a minimal daily_state dict, calls an engine method,
and asserts the resulting DailyPlayerState fields and return values.
"""

import unittest
from unittest.mock import MagicMock

from src.core.powerup_engine import PowerUpEngine
from src.core.state import DailyPlayerState


def _make_engine(
    steal_cost=3,
    retro_steal_cost=5,
    retro_jinx_ratio=0.5,
    streak_per_day=5,
    streak_cap=25,
):
    cfg = MagicMock()

    values = {
        "JBOT_STEAL_STREAK_COST": str(steal_cost),
        "JBOT_RETRO_STEAL_STREAK_COST": str(retro_steal_cost),
        "JBOT_RETRO_JINX_BONUS_RATIO": str(retro_jinx_ratio),
        "JBOT_BONUS_STREAK_PER_DAY": str(streak_per_day),
        "JBOT_BONUS_STREAK_CAP": str(streak_cap),
        "JBOT_BONUS_BEFORE_HINT": "10",
        "JBOT_BONUS_FASTEST_CSV": "10,5,1",
        "JBOT_BONUS_TRY_CSV": "20,10,5",
        "JBOT_EMOJI_FASTEST": "🥇",
        "JBOT_EMOJI_FASTEST_CSV": "🥇,🥈,🥉",
        "JBOT_EMOJI_FIRST_TRY": "🎯",
        "JBOT_EMOJI_STREAK": "🔥",
        "JBOT_EMOJI_BEFORE_HINT": "🧠",
    }

    cfg.get.side_effect = lambda key, default=None: values.get(key, default)
    return PowerUpEngine(cfg)


def _state(**kwargs) -> DailyPlayerState:
    """Convenience: create a DailyPlayerState with fields set from kwargs."""
    s = DailyPlayerState()
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


# ---------------------------------------------------------------------------
# _get_state
# ---------------------------------------------------------------------------


class TestGetState(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()

    def test_creates_new_entry_when_missing(self):
        ds = {}
        state = self.engine._get_state(ds, "p1")
        self.assertIn("p1", ds)
        self.assertIsInstance(state, DailyPlayerState)

    def test_returns_existing_entry(self):
        existing = _state(score_earned=42)
        ds = {"p1": existing}
        result = self.engine._get_state(ds, "p1")
        self.assertIs(result, existing)


# ---------------------------------------------------------------------------
# apply_jinx
# ---------------------------------------------------------------------------


class TestApplyJinx(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine(retro_jinx_ratio=0.5)

    def test_silences_attacker(self):
        ds = {}
        self.engine.apply_jinx(ds, "att", "tgt")
        self.assertTrue(ds["att"].silenced)

    def test_sets_jinxed_by_on_target(self):
        ds = {}
        self.engine.apply_jinx(ds, "att", "tgt")
        self.assertEqual(ds["tgt"].jinxed_by, "att")

    def test_returns_zero_when_target_not_answered(self):
        ds = {}
        result = self.engine.apply_jinx(ds, "att", "tgt")
        self.assertEqual(result, 0)

    def test_no_score_transfer_when_target_not_answered(self):
        ds = {}
        self.engine.apply_jinx(ds, "att", "tgt")
        self.assertEqual(ds.get("att", DailyPlayerState()).score_earned, 0)

    def test_retro_transfers_half_streak_bonus(self):
        ds = {
            "tgt": _state(is_correct=True, score_earned=100, bonuses={"streak": 20}),
        }
        transferred = self.engine.apply_jinx(ds, "att", "tgt")
        self.assertEqual(transferred, 10)  # int(20 * 0.5)
        self.assertEqual(ds["tgt"].score_earned, 90)
        self.assertEqual(ds["att"].score_earned, 10)

    def test_retro_strips_streak_from_target_bonuses(self):
        ds = {"tgt": _state(is_correct=True, bonuses={"streak": 20})}
        self.engine.apply_jinx(ds, "att", "tgt")
        self.assertNotIn("streak", ds["tgt"].bonuses)

    def test_retro_zero_transfer_when_no_streak_bonus(self):
        ds = {"tgt": _state(is_correct=True, bonuses={}, score_earned=50)}
        transferred = self.engine.apply_jinx(ds, "att", "tgt")
        self.assertEqual(transferred, 0)
        self.assertEqual(ds["tgt"].score_earned, 50)

    def test_retro_jinxed_by_still_set_on_zero_transfer(self):
        ds = {"tgt": _state(is_correct=True, bonuses={})}
        self.engine.apply_jinx(ds, "att", "tgt")
        self.assertEqual(ds["tgt"].jinxed_by, "att")

    def test_ratio_floor_truncates(self):
        """int() truncates, so odd amounts lose the remainder."""
        ds = {"tgt": _state(is_correct=True, score_earned=100, bonuses={"streak": 7})}
        transferred = self.engine.apply_jinx(ds, "att", "tgt")
        self.assertEqual(transferred, 3)  # int(7 * 0.5) = 3

    def test_custom_ratio_applied(self):
        engine = _make_engine(retro_jinx_ratio=0.25)
        ds = {"tgt": _state(is_correct=True, score_earned=100, bonuses={"streak": 20})}
        transferred = engine.apply_jinx(ds, "att", "tgt")
        self.assertEqual(transferred, 5)  # int(20 * 0.25)


# ---------------------------------------------------------------------------
# apply_late_jinx
# ---------------------------------------------------------------------------


class TestApplyLateJinx(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine(retro_jinx_ratio=0.5)

    def test_strips_before_hint_cost(self):
        ds = {"att": _state(score_earned=100, bonuses={"before_hint": 10})}
        self.engine.apply_late_jinx(ds, "att", "tgt")
        self.assertNotIn("before_hint", ds["att"].bonuses)
        self.assertEqual(ds["att"].score_earned, 90)

    def test_strips_fastest_cost(self):
        ds = {"att": _state(score_earned=100, bonuses={"fastest_1": 10, "fastest": 10})}
        self.engine.apply_late_jinx(ds, "att", "tgt")
        self.assertNotIn("fastest_1", ds["att"].bonuses)
        self.assertNotIn("fastest", ds["att"].bonuses)
        self.assertEqual(ds["att"].score_earned, 90)

    def test_returns_cost_and_transferred(self):
        ds = {
            "att": _state(
                score_earned=150, bonuses={"before_hint": 10, "fastest_1": 10}
            ),
            "tgt": _state(is_correct=True, score_earned=100, bonuses={"streak": 20}),
        }
        cost, transferred = self.engine.apply_late_jinx(ds, "att", "tgt")
        self.assertEqual(cost, 20)
        self.assertEqual(transferred, 10)

    def test_sets_silenced_and_jinxed_by(self):
        ds = {"att": _state(score_earned=50, bonuses={})}
        self.engine.apply_late_jinx(ds, "att", "tgt")
        self.assertTrue(ds["att"].silenced)
        self.assertEqual(ds["tgt"].jinxed_by, "att")

    def test_zero_cost_when_no_strippable_bonuses(self):
        ds = {"att": _state(score_earned=100, bonuses={"streak": 20})}
        cost, _ = self.engine.apply_late_jinx(ds, "att", "tgt")
        self.assertEqual(cost, 0)
        self.assertEqual(ds["att"].score_earned, 100)


# ---------------------------------------------------------------------------
# resolve_jinx_on_correct
# ---------------------------------------------------------------------------


class TestResolveJinxOnCorrect(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()

    def test_returns_zero_when_no_jinx(self):
        ds = {"tgt": _state()}
        bonus_values = {"streak": 15}
        result = self.engine.resolve_jinx_on_correct(ds, "tgt", bonus_values)
        self.assertEqual(result, 0)

    def test_transfers_streak_bonus_to_attacker(self):
        ds = {
            "tgt": _state(jinxed_by="att"),
            "att": _state(score_earned=0),
        }
        bonus_values = {"streak": 15}
        transferred = self.engine.resolve_jinx_on_correct(ds, "tgt", bonus_values)
        self.assertEqual(transferred, 15)
        self.assertEqual(ds["att"].score_earned, 15)

    def test_strips_streak_from_bonus_values(self):
        ds = {"tgt": _state(jinxed_by="att")}
        bonus_values = {"streak": 15, "before_hint": 10}
        self.engine.resolve_jinx_on_correct(ds, "tgt", bonus_values)
        self.assertNotIn("streak", bonus_values)
        self.assertIn("before_hint", bonus_values)

    def test_returns_zero_when_no_streak_bonus(self):
        ds = {"tgt": _state(jinxed_by="att")}
        bonus_values = {"before_hint": 10}
        result = self.engine.resolve_jinx_on_correct(ds, "tgt", bonus_values)
        self.assertEqual(result, 0)


# ---------------------------------------------------------------------------
# apply_steal — preload
# ---------------------------------------------------------------------------


class TestApplyStealPreload(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()

    def test_sets_stealing_from_and_preload_flag(self):
        ds = {}
        self.engine.apply_steal(ds, "thief", "tgt", initial_streak=5, is_preload=True)
        self.assertEqual(ds["thief"].stealing_from, "tgt")
        self.assertTrue(ds["thief"].steal_is_preload)

    def test_sets_steal_attempt_by_on_target(self):
        ds = {}
        self.engine.apply_steal(ds, "thief", "tgt", initial_streak=5, is_preload=True)
        self.assertEqual(ds["tgt"].steal_attempt_by, "thief")

    def test_returns_zero_zero_for_preload(self):
        ds = {}
        result = self.engine.apply_steal(
            ds, "thief", "tgt", initial_streak=5, is_preload=True
        )
        self.assertEqual(result, (0, 0, 0))

    def test_no_streak_delta_for_preload(self):
        ds = {}
        self.engine.apply_steal(ds, "thief", "tgt", initial_streak=5, is_preload=True)
        self.assertEqual(ds["thief"].streak_delta, 0)


# ---------------------------------------------------------------------------
# apply_steal — normal forward (target not answered)
# ---------------------------------------------------------------------------


class TestApplyStealNormal(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine(steal_cost=3)

    def test_sets_streak_delta(self):
        ds = {}
        self.engine.apply_steal(ds, "thief", "tgt", initial_streak=5)
        self.assertEqual(ds["thief"].streak_delta, -3)

    def test_streak_delta_does_not_go_below_negative_initial(self):
        """If initial < cost, delta is capped at -initial."""
        ds = {}
        self.engine.apply_steal(ds, "thief", "tgt", initial_streak=2)
        self.assertEqual(ds["thief"].streak_delta, -2)

    def test_sets_stealing_from_and_attempt_on_target(self):
        ds = {}
        self.engine.apply_steal(ds, "thief", "tgt", initial_streak=5)
        self.assertEqual(ds["thief"].stealing_from, "tgt")
        self.assertEqual(ds["tgt"].steal_attempt_by, "thief")

    def test_returns_cost_and_zero_stolen(self):
        ds = {}
        deducted, stolen, bonus_delta = self.engine.apply_steal(
            ds, "thief", "tgt", initial_streak=5
        )
        self.assertEqual(deducted, 3)
        self.assertEqual(stolen, 0)
        self.assertEqual(bonus_delta, 0)  # thief not yet answered

    def test_no_score_change_for_forward_steal(self):
        ds = {}
        self.engine.apply_steal(ds, "thief", "tgt", initial_streak=5)
        self.assertEqual(ds["thief"].score_earned, 0)

    def test_thief_already_answered_sets_adjusted_streak_delta(self):
        """When thief already answered, effective streak = initial+1; delta accounts for that."""
        ds = {
            "thief": _state(is_correct=True, score_earned=100, bonuses={"streak": 25}),
        }
        self.engine.apply_steal(ds, "thief", "tgt", initial_streak=5)
        # effective=6, cost=3, new_bonus_streak=3, delta=3-5=-2
        self.assertEqual(ds["thief"].streak_delta, -2)

    def test_thief_already_answered_recalculates_streak_bonus(self):
        """Bonus is recalculated using effective-cost formula and returned as bonus_delta."""
        ds = {
            "thief": _state(is_correct=True, score_earned=100, bonuses={"streak": 25}),
        }
        deducted, stolen, bonus_delta = self.engine.apply_steal(
            ds, "thief", "tgt", initial_streak=5
        )
        # effective=6, cost=3, new_bonus_streak=3, get_streak_bonus(3)=15, delta=15-25=-10
        self.assertEqual(bonus_delta, -10)
        self.assertEqual(ds["thief"].score_earned, 90)  # 100 + (-10)
        self.assertEqual(ds["thief"].bonuses.get("streak"), 15)


# ---------------------------------------------------------------------------
# apply_steal — retroactive (target already answered)
# ---------------------------------------------------------------------------


class TestApplyStealRetro(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine(steal_cost=3, retro_steal_cost=5)

    def test_transfers_stealable_bonuses_immediately(self):
        ds = {
            "tgt": _state(
                is_correct=True,
                score_earned=50,
                bonuses={"before_hint": 10, "try_1": 20},
            ),
        }
        self.engine.apply_steal(ds, "thief", "tgt", initial_streak=3)
        # pop_stealable_bonuses transfers try_1 + before_hint = 30
        transferred = ds["thief"].score_earned
        self.assertGreater(transferred, 0)
        self.assertEqual(ds["tgt"].score_earned + transferred, 50)

    def test_uses_retro_cost_for_streak_delta(self):
        ds = {"tgt": _state(is_correct=True)}
        self.engine.apply_steal(ds, "thief", "tgt", initial_streak=5)
        # thief not yet answered → streak_delta = -min(5, 5) = -5
        self.assertEqual(ds["thief"].streak_delta, -5)

    def test_returns_retro_cost_and_stolen_amount(self):
        ds = {
            "tgt": _state(
                is_correct=True, score_earned=50, bonuses={"before_hint": 10}
            ),
        }
        deducted, stolen, bonus_delta = self.engine.apply_steal(
            ds, "thief", "tgt", initial_streak=5
        )
        self.assertEqual(deducted, 5)
        self.assertEqual(stolen, 10)
        self.assertEqual(bonus_delta, 0)  # thief not yet answered

    def test_zero_stolen_when_no_stealable_bonuses(self):
        ds = {"tgt": _state(is_correct=True, bonuses={})}
        deducted, stolen, bonus_delta = self.engine.apply_steal(
            ds, "thief", "tgt", initial_streak=5
        )
        self.assertEqual(stolen, 0)
        self.assertEqual(bonus_delta, 0)

    def test_marks_steal_attempt_on_target(self):
        ds = {"tgt": _state(is_correct=True)}
        self.engine.apply_steal(ds, "thief", "tgt", initial_streak=5)
        self.assertEqual(ds["tgt"].steal_attempt_by, "thief")

    def test_thief_already_answered_uses_retro_cost_for_streak_delta(self):
        """When both thief + target answered, effective = initial+1, cost = retro_cost."""
        ds = {
            "thief": _state(is_correct=True, score_earned=100, bonuses={"streak": 25}),
            "tgt": _state(is_correct=True),
        }
        deducted, stolen, bonus_delta = self.engine.apply_steal(
            ds, "thief", "tgt", initial_streak=5
        )
        # effective=6, retro_cost=5, new_bonus_streak=1, delta=1-5=-4
        self.assertEqual(ds["thief"].streak_delta, -4)
        # new_bonus_streak=1 → get_streak_bonus(1)=0, delta=0-25=-25
        self.assertEqual(bonus_delta, -25)


# ---------------------------------------------------------------------------
# resolve_steal_on_correct
# ---------------------------------------------------------------------------


class TestResolveStealOnCorrect(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()

    def test_returns_zero_when_no_pending_steal(self):
        ds = {"tgt": _state()}
        result = self.engine.resolve_steal_on_correct(ds, "tgt")
        self.assertEqual(result, 0)

    def test_transfers_stealable_amount(self):
        ds = {
            "tgt": _state(
                steal_attempt_by="thief", score_earned=50, bonuses={"before_hint": 10}
            ),
            "thief": _state(score_earned=0),
        }
        stolen = self.engine.resolve_steal_on_correct(ds, "tgt")
        self.assertEqual(stolen, 10)
        self.assertEqual(ds["tgt"].score_earned, 40)
        self.assertEqual(ds["thief"].score_earned, 10)

    def test_clears_steal_attempt_by(self):
        ds = {
            "tgt": _state(steal_attempt_by="thief", bonuses={"before_hint": 10}),
            "thief": _state(),
        }
        self.engine.resolve_steal_on_correct(ds, "tgt")
        self.assertIsNone(ds["tgt"].steal_attempt_by)

    def test_clears_attempt_even_when_nothing_stolen(self):
        ds = {"tgt": _state(steal_attempt_by="thief", bonuses={})}
        self.engine.resolve_steal_on_correct(ds, "tgt")
        self.assertIsNone(ds["tgt"].steal_attempt_by)


# ---------------------------------------------------------------------------
# apply_rest
# ---------------------------------------------------------------------------


class TestApplyRest(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()

    def test_marks_player_as_resting(self):
        ds = {}
        self.engine.apply_rest(ds, "p1")
        self.assertTrue(ds["p1"].is_resting)

    def test_returns_none_none_when_no_attacks(self):
        ds = {}
        result = self.engine.apply_rest(ds, "p1")
        self.assertEqual(result, (None, None))

    def test_whiffs_pending_jinx(self):
        ds = {"p1": _state(jinxed_by="att")}
        jinx_id, steal_id = self.engine.apply_rest(ds, "p1")
        self.assertEqual(jinx_id, "att")
        self.assertIsNone(ds["p1"].jinxed_by)

    def test_whiffs_pending_steal(self):
        ds = {"p1": _state(steal_attempt_by="thief")}
        jinx_id, steal_id = self.engine.apply_rest(ds, "p1")
        self.assertEqual(steal_id, "thief")
        self.assertIsNone(ds["p1"].steal_attempt_by)

    def test_whiffs_both_attacks(self):
        ds = {"p1": _state(jinxed_by="att", steal_attempt_by="thief")}
        jinx_id, steal_id = self.engine.apply_rest(ds, "p1")
        self.assertEqual(jinx_id, "att")
        self.assertEqual(steal_id, "thief")


# ---------------------------------------------------------------------------
# apply_preload_jinx / apply_preload_steal
# ---------------------------------------------------------------------------


class TestPreloads(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()

    def test_preload_jinx_silences_attacker(self):
        ds = {}
        self.engine.apply_preload_jinx(ds, "att", "tgt")
        self.assertTrue(ds["att"].silenced)

    def test_preload_jinx_sets_jinxed_by_on_target(self):
        ds = {}
        self.engine.apply_preload_jinx(ds, "att", "tgt")
        self.assertEqual(ds["tgt"].jinxed_by, "att")

    def test_preload_steal_sets_flags(self):
        ds = {}
        self.engine.apply_preload_steal(ds, "thief", "tgt")
        self.assertEqual(ds["thief"].stealing_from, "tgt")
        self.assertTrue(ds["thief"].steal_is_preload)
        self.assertEqual(ds["tgt"].steal_attempt_by, "thief")


# ---------------------------------------------------------------------------
# strip_late_day_jinx_cost
# ---------------------------------------------------------------------------


class TestStripLateDayJinxCost(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()

    def test_strips_before_hint(self):
        ds = {"p1": _state(score_earned=100, bonuses={"before_hint": 10})}
        cost = self.engine.strip_late_day_jinx_cost(ds, "p1")
        self.assertEqual(cost, 10)
        self.assertNotIn("before_hint", ds["p1"].bonuses)
        self.assertEqual(ds["p1"].score_earned, 90)

    def test_strips_fastest_ranked_bonuses(self):
        ds = {"p1": _state(score_earned=100, bonuses={"fastest_1": 10, "fastest_2": 5})}
        cost = self.engine.strip_late_day_jinx_cost(ds, "p1")
        self.assertEqual(cost, 15)
        self.assertNotIn("fastest_1", ds["p1"].bonuses)

    def test_strips_fastest_alias(self):
        ds = {"p1": _state(score_earned=100, bonuses={"fastest": 10})}
        self.engine.strip_late_day_jinx_cost(ds, "p1")
        self.assertNotIn("fastest", ds["p1"].bonuses)

    def test_ignores_streak_and_other_bonuses(self):
        ds = {"p1": _state(score_earned=100, bonuses={"streak": 20, "try_1": 20})}
        cost = self.engine.strip_late_day_jinx_cost(ds, "p1")
        self.assertEqual(cost, 0)
        self.assertIn("streak", ds["p1"].bonuses)
        self.assertIn("try_1", ds["p1"].bonuses)

    def test_returns_zero_when_nothing_to_strip(self):
        ds = {"p1": _state(score_earned=100, bonuses={})}
        cost = self.engine.strip_late_day_jinx_cost(ds, "p1")
        self.assertEqual(cost, 0)


# ---------------------------------------------------------------------------
# recalculate_streak_bonus
# ---------------------------------------------------------------------------


class TestRecalculateStreakBonus(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine(streak_per_day=5, streak_cap=25)

    def test_reduces_bonus_and_updates_score(self):
        ds = {"p1": _state(score_earned=100, bonuses={"streak": 25})}
        delta = self.engine.recalculate_streak_bonus(ds, "p1", new_streak=2)
        # get_streak_bonus(2) = min(2*5, 25) = 10; old=25; delta=-15
        self.assertEqual(delta, -15)
        self.assertEqual(ds["p1"].score_earned, 85)
        self.assertEqual(ds["p1"].bonuses.get("streak"), 10)

    def test_removes_streak_key_when_new_bonus_zero(self):
        ds = {"p1": _state(score_earned=100, bonuses={"streak": 25})}
        self.engine.recalculate_streak_bonus(ds, "p1", new_streak=0)
        self.assertNotIn("streak", ds["p1"].bonuses)

    def test_sets_new_streak_key_when_positive(self):
        ds = {"p1": _state(score_earned=100, bonuses={})}
        self.engine.recalculate_streak_bonus(ds, "p1", new_streak=3)
        self.assertIn("streak", ds["p1"].bonuses)
        self.assertEqual(ds["p1"].bonuses["streak"], 15)

    def test_returns_zero_delta_when_bonus_unchanged(self):
        ds = {"p1": _state(score_earned=100, bonuses={"streak": 15})}
        delta = self.engine.recalculate_streak_bonus(ds, "p1", new_streak=3)
        self.assertEqual(delta, 0)
        self.assertEqual(ds["p1"].score_earned, 100)

    def test_positive_delta_when_bonus_increases(self):
        ds = {"p1": _state(score_earned=100, bonuses={"streak": 10})}
        delta = self.engine.recalculate_streak_bonus(ds, "p1", new_streak=4)
        # new_bonus = min(4*5, 25) = 20; old=10; delta=+10
        self.assertEqual(delta, 10)
        self.assertEqual(ds["p1"].score_earned, 110)


if __name__ == "__main__":
    unittest.main()
