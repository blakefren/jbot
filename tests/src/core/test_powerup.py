"""
Unit tests for PowerUpManager — live-game orchestration layer.

Tests are organised by feature area so each class has a single, clear concern:

    TestRestBehavior              — REST: freeze streak, multiplier, cancel attacks
    TestJinxBehavior              — JINX forward (early-attacker) mechanics
    TestStealBehavior             — STEAL forward (early-attacker) mechanics
    TestGuards                    — Blocking rules: one per day, invalid players,
                                    duplicate targets, overnight vs. active question
    TestCanAnswer                 — Silence gating (jinxed players)
    TestDailyStateManagement      — State reset and simulator-state restore
    TestStealEnforcementAndScaling — Zero-streak rejection and partial-steal scaling
                                     (owns its own fixture with different players)
"""

import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock

from src.core.events import GuessContext
from src.core.player import Player
from src.core.powerup import PowerUpError, PowerUpManager
from src.core.state import DailyPlayerState

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


class _PowerUpManagerTests(unittest.TestCase):
    """
    Base class providing a common three-player fixture and a fresh
    PowerUpManager (self.manager) for each test.

    Players:
      "1" — P1, score=100, streak=3
      "2" — P2, score=100, streak=5
      "3" — P3, score=100, streak=0  (useful for no-streak edge cases)

    Subclasses may mutate self.players, self.manager, self.data_manager, and
    self.player_manager freely without affecting other tests.
    """

    def setUp(self):
        self.player_manager = MagicMock()
        self.data_manager = MagicMock()
        self.players = {
            "1": Player(id="1", name="P1", score=100, answer_streak=3),
            "2": Player(id="2", name="P2", score=100, answer_streak=5),
            "3": Player(id="3", name="P3", score=100, answer_streak=0),
        }
        self.player_manager.get_player.side_effect = lambda pid: self.players.get(pid)
        # Default: player last answered yesterday â†’ not in late-day mode
        self.data_manager.get_last_correct_guess_date.return_value = (
            date.today() - timedelta(days=1)
        )
        self.data_manager.get_today.return_value = date.today()

        def update_score(pid, amount):
            if pid in self.players:
                self.players[pid].score += amount

        def reset_streak(pid):
            if pid in self.players:
                self.players[pid].answer_streak = 0

        def set_streak(pid, value):
            if pid in self.players:
                self.players[pid].answer_streak = value

        self.player_manager.update_score.side_effect = update_score
        self.player_manager.reset_streak.side_effect = reset_streak
        self.player_manager.set_streak.side_effect = set_streak

        self.data_manager.get_pending_multiplier.return_value = 0.0
        self.data_manager.get_pending_powerup.return_value = None
        self.data_manager.get_pending_powerup_for_target.return_value = None

        self.manager = PowerUpManager(self.player_manager, self.data_manager)


# ---------------------------------------------------------------------------
# REST
# ---------------------------------------------------------------------------


class TestRestBehavior(_PowerUpManagerTests):
    """REST: freeze streak, store multiplier for next day, cancel incoming attacks."""

    def test_rest_basic(self):
        """Rest marks player as resting, stores the multiplier, reveals answer privately."""
        public_msg, private_msg = self.manager.rest("1", "q1", "Correct Answer")
        self.assertIn("resting", public_msg)
        self.assertIn("Correct Answer", private_msg)
        self.assertTrue(self.manager._get_daily_state("1").is_resting)
        self.data_manager.set_pending_multiplier.assert_called_once_with("1", 1.2)

    def test_rest_already_answered(self):
        """Rest is blocked when the player has already answered correctly today."""
        self.data_manager.get_last_correct_guess_date.return_value = date.today()
        with self.assertRaises(PowerUpError) as cm:
            self.manager.rest("1", "q1", "Correct Answer")
        self.assertIn("already answered correctly", str(cm.exception))

    def test_rest_blocks_guesses(self):
        """A resting player cannot submit guesses."""
        self.manager._get_daily_state("1").is_resting = True
        can_answer, reason = self.manager.can_answer("1")
        self.assertFalse(can_answer)
        self.assertIn("resting", reason)

    def test_rest_cancels_incoming_steal(self):
        """Rest cancels a pending steal; steal_attempt_by is cleared."""
        self.manager._get_daily_state("2").steal_attempt_by = "1"
        public_msg, _ = self.manager.rest("2", "q1", "Ans")
        self.assertIn("whiffed", public_msg)
        self.assertIsNone(self.manager._get_daily_state("2").steal_attempt_by)

    def test_rest_cancels_incoming_jinx(self):
        """Rest cancels a pending jinx; jinxed_by is cleared."""
        self.manager._get_daily_state("2").jinxed_by = "1"
        public_msg, _ = self.manager.rest("2", "q1", "Ans")
        self.assertIn("no effect", public_msg)
        self.assertIsNone(self.manager._get_daily_state("2").jinxed_by)

    def test_rest_next_day_multiplier(self):
        """1.2x rest multiplier is applied to the player's next correct answer."""
        self.data_manager.get_pending_multiplier.return_value = 1.2
        ctx = GuessContext(1, "P1", "ans", True, points_earned=100)
        msgs = self.manager.on_guess(ctx)
        self.assertTrue(any("Rest bonus" in m for m in msgs))
        self.assertEqual(self.players["1"].score, 120)
        self.data_manager.clear_pending_multiplier.assert_called_once_with("1")


# ---------------------------------------------------------------------------
# JINX
# ---------------------------------------------------------------------------


class TestJinxBehavior(_PowerUpManagerTests):
    """JINX forward mechanics: silence attacker, transfer streak bonus when target answers."""

    def test_jinx_silences_attacker(self):
        """Activating jinx silences the attacker until the hint is sent."""
        self.manager.jinx("1", "2", "q1")
        self.assertTrue(self.manager._get_daily_state("1").silenced)

    def test_jinx_marks_target(self):
        """Activating jinx records jinxed_by on the target."""
        self.manager.jinx("1", "2", "q1")
        self.assertEqual(self.manager._get_daily_state("2").jinxed_by, "1")

    def test_jinx_no_immediate_score_change(self):
        """Activating jinx does not immediately change scores."""
        self.manager.jinx("1", "2", "q1")
        self.assertEqual(self.players["1"].score, 100)
        self.assertEqual(self.players["2"].score, 100)

    def test_jinx_transfers_streak_bonus_on_answer(self):
        """When the jinxed target answers, their full streak bonus is transferred to the attacker."""
        self.manager.jinx("1", "2", "q1")
        self.players["2"].answer_streak = 6
        bonus_messages = ["🔥 6 day streak! (+25)"]
        ctx = GuessContext(
            2,
            "P2",
            "ans",
            True,
            points_earned=125,
            bonus_values={"streak": 25},
            bonus_messages=bonus_messages,
        )
        self.manager.on_guess(ctx)
        self.assertEqual(self.players["1"].score, 125)  # +25 stolen
        self.assertEqual(self.players["2"].score, 75)  # -25 stolen
        self.assertEqual(ctx.points_earned, 100)  # ctx reflects net score
        self.assertEqual(len(bonus_messages), 0)  # streak message removed

    def test_jinx_no_streak_bonus_no_effect(self):
        """If the jinxed target earns no streak bonus, nothing is transferred."""
        self.manager.jinx("1", "3", "q1")  # P3 has streak=0
        self.players["3"].answer_streak = 1
        msgs = self.manager.on_guess(
            GuessContext(3, "P3", "ans", True, points_earned=100)
        )
        self.player_manager.set_streak.assert_not_called()
        self.assertTrue(any("no streak bonus to steal" in m for m in msgs))

    def test_jinx_resolution_messages(self):
        """Resolution message names both players and the transferred amount."""
        self.manager.jinx("1", "2", "q1")
        msgs = self.manager.on_guess(
            GuessContext(
                2, "P2", "ans", True, points_earned=100, bonus_values={"streak": 50}
            )
        )
        self.assertTrue(any("swiped" in m and "streak bonus" in m for m in msgs))
        self.assertEqual(self.players["1"].score, 150)
        self.assertEqual(self.players["2"].score, 50)

    def test_duplicate_jinx_on_same_target_blocked(self):
        """A second jinx on the same target is blocked and the attempt is not logged."""
        self.manager.jinx("1", "2", "q1")
        self.assertEqual(self.data_manager.log_powerup_usage.call_count, 1)
        with self.assertRaises(PowerUpError) as cm:
            self.manager.jinx("3", "2", "q1")
        self.assertIn("already been jinxed", str(cm.exception))
        self.assertEqual(self.data_manager.log_powerup_usage.call_count, 1)


# ---------------------------------------------------------------------------
# STEAL
# ---------------------------------------------------------------------------


class TestStealBehavior(_PowerUpManagerTests):
    """STEAL forward mechanics: deduct streak upfront, transfer non-streak bonuses on answer."""

    def test_steal_deducts_streak_immediately(self):
        """Steal immediately deducts streak days from the thief."""
        self.manager.steal("1", "2", "q1")
        expected = max(0, 3 - self.manager.engine.steal_streak_cost)
        self.assertEqual(self.players["1"].answer_streak, expected)

    def test_steal_transfers_bonuses_on_target_answer(self):
        """Non-streak bonuses are transferred to the thief when the target answers correctly."""
        self.manager.steal("1", "2", "q1")
        ctx = GuessContext(
            2, "P2", "ans", True, points_earned=100, bonus_values={"fastest": 10}
        )
        msgs = self.manager.on_guess(ctx)
        self.assertTrue(any("stole 10 pts" in m for m in msgs))
        self.assertEqual(self.players["1"].score, 110)
        self.assertEqual(self.players["2"].score, 90)

    def test_steal_no_stealable_bonuses(self):
        """When the target has no stealable bonuses, no transfer occurs."""
        self.manager.steal("1", "2", "q1")
        msgs = self.manager.on_guess(GuessContext(1, "P1", "ans", True))
        self.assertFalse(any("stole" in m for m in msgs))

    def test_steal_first_try_bonus(self):
        """First-try bonus is included in the stealable pool."""
        self.manager.steal("1", "2", "q1")
        msgs = self.manager.on_guess(
            GuessContext(
                2, "P2", "ans", True, points_earned=120, bonus_values={"first_try": 20}
            )
        )
        self.assertTrue(any("stole 20 pts" in m for m in msgs))
        self.assertEqual(self.players["1"].score, 120)
        self.assertEqual(self.players["2"].score, 80)

    def test_steal_includes_rest_bonus(self):
        """Rest multiplier bonus earned on the answer day is included in the stealable pool."""
        self.data_manager.get_pending_multiplier.side_effect = lambda pid: (
            1.2 if pid == "2" else 0.0
        )
        self.manager.steal("1", "2", "q1")
        # base=100, before_hint=10 -> 110 pts; rest bonus = round(110x0.2) = 22
        # stealable = before_hint(10) + rest(22) = 32
        msgs = self.manager.on_guess(
            GuessContext(
                2,
                "P2",
                "ans",
                True,
                points_earned=110,
                bonus_values={"before_hint": 10},
                question_id="q1",
            )
        )
        self.assertTrue(
            any("stole 32 pts" in m for m in msgs),
            f"Expected steal of 32 pts (10 before_hint + 22 rest). Messages: {msgs}",
        )
        self.assertEqual(self.players["1"].score, 132)
        self.assertEqual(self.players["2"].score, 90)

    def test_steal_resolution_messages(self):
        """Resolution message reports the combined stolen amount."""
        self.manager.steal("1", "2", "q1")
        msgs = self.manager.on_guess(
            GuessContext(
                2,
                "P2",
                "ans",
                True,
                points_earned=100,
                bonus_values={"fastest": 20, "first_try": 10},
            )
        )
        self.assertTrue(any("stole 30 pts" in m for m in msgs))

    def test_duplicate_steal_on_same_target_blocked(self):
        """A second steal on the same target is blocked and the attempt is not logged."""
        self.manager.steal("1", "2", "q1")
        self.assertEqual(self.data_manager.log_powerup_usage.call_count, 1)
        with self.assertRaises(PowerUpError) as cm:
            self.manager.steal("3", "2", "q1")
        self.assertIn("already being targeted for theft", str(cm.exception))
        self.assertEqual(self.data_manager.log_powerup_usage.call_count, 1)


# ---------------------------------------------------------------------------
# Guards (blocking / enforcement)
# ---------------------------------------------------------------------------


class TestGuards(_PowerUpManagerTests):
    """
    Blocking rules: one power-up per player per day, invalid players,
    duplicate targets, and overnight vs. active-question constraints.
    """

    # --- one power-up per day ---

    def test_second_jinx_by_same_attacker_blocked(self):
        """A player cannot use jinx twice in one day."""
        self.manager.jinx("1", "2", "q1")
        with self.assertRaises(PowerUpError) as cm:
            self.manager.jinx("1", "3", "q1")
        self.assertIn("already used a power-up today", str(cm.exception))

    def test_second_steal_by_same_attacker_blocked(self):
        """A player cannot use steal twice in one day."""
        self.manager.steal("1", "2", "q1")
        with self.assertRaises(PowerUpError) as cm:
            self.manager.steal("1", "3", "q1")
        self.assertIn("already used a power-up today", str(cm.exception))

    def test_steal_blocked_after_jinx(self):
        """A player who already jinxed cannot then steal."""
        self.manager.jinx("1", "2", "q1")
        with self.assertRaises(PowerUpError) as cm:
            self.manager.steal("1", "3", "q1")
        self.assertIn("already used a power-up today", str(cm.exception))

    def test_jinx_blocked_after_rest(self):
        """A player who already rested cannot then jinx."""
        self.manager.rest("1", "q1", "Ans")
        with self.assertRaises(PowerUpError) as cm:
            self.manager.jinx("1", "2", "q1")
        self.assertIn("already used a power-up today", str(cm.exception))

    # --- invalid players ---

    def test_jinx_invalid_attacker(self):
        """Jinx raises PowerUpError when the attacker is not a registered player."""
        with self.assertRaises(PowerUpError) as cm:
            self.manager.jinx("999", "1", "q1")
        self.assertIn("Invalid player", str(cm.exception))

    def test_jinx_invalid_target(self):
        """Jinx raises PowerUpError when the target is not a registered player."""
        with self.assertRaises(PowerUpError) as cm:
            self.manager.jinx("1", "999", "q1")
        self.assertIn("Invalid player", str(cm.exception))

    def test_steal_invalid_target(self):
        """Steal raises PowerUpError when the target is not a registered player."""
        with self.assertRaises(PowerUpError) as cm:
            self.manager.steal("1", "999", "q1")
        self.assertIn("Invalid player", str(cm.exception))

    # --- overnight / no active question ---

    def test_overnight_jinx_queued_without_active_question(self):
        """Jinx with question_id=None queues an overnight pre-load for the next day."""
        result = self.manager.jinx("1", "2", None)
        self.assertIn("queued for tomorrow", result)

    def test_overnight_steal_queued_without_active_question(self):
        """Steal with question_id=None queues an overnight pre-load for the next day."""
        result = self.manager.steal("1", "2", None)
        self.assertIn("queued", result)

    def test_rest_requires_active_question(self):
        """Rest raises PowerUpError when no question is active."""
        with self.assertRaises(PowerUpError) as cm:
            self.manager.rest("1", None, "Ans")
        self.assertEqual(str(cm.exception), "There is no active question right now.")


# ---------------------------------------------------------------------------
# Can-answer / silence gating
# ---------------------------------------------------------------------------


class TestCanAnswer(_PowerUpManagerTests):
    """Silence gating: jinxed players are blocked from answering until the hint is sent."""

    def test_silenced_player_blocked_before_hint(self):
        """A silenced player cannot answer while the hint has not yet been sent."""
        self.manager._get_daily_state("1").silenced = True
        can_answer, reason = self.manager.can_answer("1", hint_sent=False)
        self.assertFalse(can_answer)
        self.assertIn("Jinxed", reason)

    def test_silenced_player_unblocked_after_hint(self):
        """A silenced player can answer once the hint has been sent."""
        self.manager._get_daily_state("1").silenced = True
        can_answer, _ = self.manager.can_answer("1", hint_sent=True)
        self.assertTrue(can_answer)

    def test_on_guess_correct_returns_list(self):
        msgs = self.manager.on_guess(
            GuessContext("1", "P1", "guess", True, points_earned=100)
        )
        self.assertIsInstance(msgs, list)

    def test_on_guess_incorrect_returns_empty_list(self):
        msgs = self.manager.on_guess(GuessContext("1", "P1", "guess", False))
        self.assertIsInstance(msgs, list)
        self.assertEqual(len(msgs), 0)


# ---------------------------------------------------------------------------
# Daily state management
# ---------------------------------------------------------------------------


class TestDailyStateManagement(_PowerUpManagerTests):
    """State reset (end of day) and state restore (simulator hand-off)."""

    def test_reset_clears_all_state(self):
        """reset_daily_state clears silenced, powerup_used_today, and jinxed_by."""
        self.manager.jinx("1", "2", "q1")
        self.assertTrue(self.manager._get_daily_state("1").silenced)
        self.assertTrue(self.manager._get_daily_state("1").powerup_used_today)

        self.manager.reset_daily_state()

        state = self.manager._get_daily_state("1")
        self.assertFalse(state.silenced)
        self.assertFalse(state.powerup_used_today)
        self.assertIsNone(state.jinxed_by)

    def test_restore_copies_state_fields(self):
        """restore_daily_state copies all fields from a simulated DailyPlayerState."""
        simulated = DailyPlayerState(
            jinxed_by="p2", score_earned=100, bonuses={"first_try": 20}
        )
        self.manager.restore_daily_state("p1", simulated)
        state = self.manager._get_daily_state("p1")
        self.assertEqual(state.jinxed_by, "p2")
        self.assertFalse(state.is_resting)
        self.assertEqual(state.score_earned, 100)
        self.assertEqual(state.bonuses, {"first_try": 20})

    def test_restore_powerup_used_today_when_silenced(self):
        """powerup_used_today is True when the restored state has silenced=True (jinx attacker)."""
        simulated = DailyPlayerState(silenced=True)
        self.manager.restore_daily_state("p1", simulated)
        self.assertTrue(self.manager._get_daily_state("p1").powerup_used_today)

    def test_restore_powerup_used_today_when_stealing(self):
        """powerup_used_today is True when the restored state has stealing_from set (steal attacker)."""
        simulated = DailyPlayerState(stealing_from="p2")
        self.manager.restore_daily_state("p1", simulated)
        self.assertTrue(self.manager._get_daily_state("p1").powerup_used_today)

    def test_restore_powerup_not_used_when_no_powerup(self):
        """powerup_used_today is False when the restored state has no active power-up."""
        simulated = DailyPlayerState()
        self.manager.restore_daily_state("p1", simulated)
        self.assertFalse(self.manager._get_daily_state("p1").powerup_used_today)


# ---------------------------------------------------------------------------
# Steal enforcement and partial-steal scaling  (own fixture — different players)
# ---------------------------------------------------------------------------


class TestStealEnforcementAndScaling(unittest.TestCase):
    """
    Steal enforcement (zero-streak rejection) and partial-steal bonus scaling.

    Uses a dedicated fixture with three specialised players:
      "zero"    — streak=0 (cannot steal anything)
      "partial" — streak=2 (below default cost of 3; triggers partial steal)
      "target"  — streak=5 (normal target)
    """

    def setUp(self):
        self.player_manager = MagicMock()
        self.data_manager = MagicMock()
        self.players = {
            "zero": Player(id="zero", name="Zero", score=100, answer_streak=0),
            "partial": Player(id="partial", name="Partial", score=100, answer_streak=2),
            "target": Player(id="target", name="Target", score=100, answer_streak=5),
        }
        self.player_manager.get_player.side_effect = lambda pid: self.players.get(pid)
        self.data_manager.get_last_correct_guess_date.return_value = (
            date.today() - timedelta(days=1)
        )
        self.data_manager.get_today.return_value = date.today()

        def update_score(pid, amount):
            if pid in self.players:
                self.players[pid].score += amount

        def set_streak(pid, value):
            if pid in self.players:
                self.players[pid].answer_streak = value

        self.player_manager.update_score.side_effect = update_score
        self.player_manager.set_streak.side_effect = set_streak
        self.data_manager.get_pending_multiplier.return_value = 0.0
        self.data_manager.get_pending_powerup.return_value = None
        self.data_manager.get_pending_powerup_for_target.return_value = None

    def _make_manager(self):
        return PowerUpManager(self.player_manager, self.data_manager)

    # --- zero-streak enforcement ---

    def test_zero_streak_daytime_forward_rejected(self):
        """A player with 0 streak cannot initiate a forward daytime steal."""
        m = self._make_manager()
        with self.assertRaises(PowerUpError) as cm:
            m.steal("zero", "target", "q1")
        self.assertIn("streak days", str(cm.exception))
        self.assertIsNone(m._get_daily_state("target").steal_attempt_by)

    def test_zero_streak_daytime_retro_rejected(self):
        """A player with 0 streak cannot steal retroactively after the target answers."""
        m = self._make_manager()
        m._get_daily_state("target").is_correct = True
        m._get_daily_state("target").bonuses = {"before_hint": 10}
        with self.assertRaises(PowerUpError) as cm:
            m.steal("zero", "target", "q1")
        self.assertIn("streak days", str(cm.exception))
        self.assertIn("before_hint", m._get_daily_state("target").bonuses)

    def test_zero_streak_overnight_rejected(self):
        """A player with 0 streak cannot queue an overnight steal."""
        m = self._make_manager()
        with self.assertRaises(PowerUpError) as cm:
            m.steal("zero", "target", None)
        self.assertIn("streak days", str(cm.exception))
        self.data_manager.log_powerup_usage.assert_not_called()

    def test_zero_streak_does_not_block_other_thieves(self):
        """A failed zero-streak steal attempt does not consume the target's steal slot."""
        m = self._make_manager()
        with self.assertRaises(PowerUpError):
            m.steal("zero", "target", "q1")
        self.players["partial"].answer_streak = 3
        msg = m.steal("partial", "target", "q1")
        self.assertIn("streak days", msg)

    # --- partial steal (forward) ---

    def test_partial_steal_forward_steals_fraction(self):
        """Forward steal with 2 streak days (cost 3) transfers round(bonuses x 2/3)."""
        m = self._make_manager()
        cost = m.engine.steal_streak_cost  # default 3
        m.steal("partial", "target", "q1")
        self.assertAlmostEqual(m._get_daily_state("partial").steal_ratio, 2 / cost)

        ctx = GuessContext(
            "target",
            "Target",
            "ans",
            True,
            points_earned=130,
            bonus_values={"before_hint": 10, "fastest_1": 20},
        )
        msgs = m.on_guess(ctx)
        expected_stolen = round(30 * (2 / cost))
        self.assertTrue(any(f"stole {expected_stolen} pts" in msg for msg in msgs))
        self.assertEqual(self.players["partial"].score, 100 + expected_stolen)
        self.assertEqual(self.players["target"].score, 100 - expected_stolen)

    def test_partial_steal_forward_clears_target_bonuses(self):
        """After a partial forward steal resolves, the target's bonus dict is empty."""
        m = self._make_manager()
        m.steal("partial", "target", "q1")
        m.on_guess(
            GuessContext(
                "target",
                "Target",
                "ans",
                True,
                points_earned=120,
                bonus_values={"before_hint": 10, "fastest_1": 10},
            )
        )
        self.assertEqual(m._get_daily_state("target").bonuses, {})
        self.assertIsNone(m._get_daily_state("target").steal_attempt_by)

    # --- partial steal (retroactive) ---

    def test_partial_steal_retro_steals_fraction(self):
        """Retro steal with 2 streak days (cost 5) transfers round(bonuses x 2/5) immediately."""
        m = self._make_manager()
        retro_cost = m.engine.retro_steal_streak_cost  # default 5
        tgt = m._get_daily_state("target")
        tgt.is_correct = True
        tgt.score_earned = 130
        tgt.bonuses = {"before_hint": 10, "fastest_1": 20}
        m.steal("partial", "target", "q1")
        expected_stolen = round(30 * (2 / retro_cost))
        self.assertEqual(self.players["partial"].score, 100 + expected_stolen)
        self.assertEqual(self.players["target"].score, 100 - expected_stolen)

    def test_partial_steal_retro_clears_target_bonuses(self):
        """After a retroactive partial steal, the target's bonus dict is cleared."""
        m = self._make_manager()
        tgt = m._get_daily_state("target")
        tgt.is_correct = True
        tgt.score_earned = 110
        tgt.bonuses = {"before_hint": 10}
        m.steal("partial", "target", "q1")
        self.assertEqual(m._get_daily_state("target").bonuses, {})


if __name__ == "__main__":
    unittest.main()
