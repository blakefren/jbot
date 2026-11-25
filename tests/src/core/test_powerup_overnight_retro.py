"""
Tests for overnight powerup pre-loading (Feature A) and retroactive targeting (Feature B).
"""

import unittest
from datetime import datetime

from data.readers.question import Question
from src.core.daily_game_simulator import DailyGameSimulator
from src.core.events import GuessContext, GuessEvent, PowerUpEvent
from src.core.player import Player
from src.core.powerup import PowerUpError, PowerUpManager
from src.core.state import DailyPlayerState
from tests.src.core._powerup_helpers import make_config as _make_config
from tests.src.core._powerup_helpers import make_stack


def _make_manager(test_case):
    """Build a PowerUpManager on a real in-memory database (attacker, target, third)."""
    stack = make_stack(
        test_case,
        [
            ("attacker", "Attacker", 100, 5),
            ("target", "Target", 100, 4),
            ("third", "Third", 100, 3),
        ],
    )
    manager = PowerUpManager(stack.player_manager, stack.data_manager, _make_config())
    return manager, stack


# ---------------------------------------------------------------------------
# Feature A: Overnight pre-loading
# ---------------------------------------------------------------------------


class TestOvernightJinx(unittest.TestCase):
    def test_overnight_jinx_logs_preload_type(self):
        manager, stack = _make_manager(self)
        result = manager.jinx("attacker", "target", question_id=None)
        self.assertEqual(stack.usages(), [("attacker", "jinx_preload", "target", None)])
        self.assertIn("queued for tomorrow", result)

    def test_overnight_jinx_silences_attacker_immediately(self):
        manager, stack = _make_manager(self)
        manager.jinx("attacker", "target", question_id=None)
        self.assertTrue(manager._get_daily_state("attacker").silenced)

    def test_overnight_jinx_blocks_if_already_queued(self):
        manager, stack = _make_manager(self)
        stack.data_manager.log_powerup_usage("attacker", "jinx_preload", "third", None)
        with self.assertRaises(PowerUpError) as cm:
            manager.jinx("attacker", "target", question_id=None)
        self.assertIn("already have a powerup queued", str(cm.exception))
        self.assertEqual(len(stack.usages()), 1)

    def test_overnight_jinx_blocks_duplicate_target(self):
        manager, stack = _make_manager(self)
        stack.data_manager.log_powerup_usage("third", "jinx_preload", "target", None)
        with self.assertRaises(PowerUpError) as cm:
            manager.jinx("attacker", "target", question_id=None)
        self.assertIn("already being targeted", str(cm.exception))
        self.assertEqual(len(stack.usages()), 1)


class TestOvernightSteal(unittest.TestCase):
    def test_overnight_steal_logs_preload_type(self):
        manager, stack = _make_manager(self)
        manager.steal("attacker", "target", question_id=None)
        self.assertEqual(
            stack.usages(), [("attacker", "steal_preload", "target", None)]
        )

    def test_overnight_steal_does_not_deduct_streak_immediately(self):
        manager, stack = _make_manager(self)
        initial_streak = stack.players["attacker"].answer_streak  # 5
        manager.steal("attacker", "target", question_id=None)
        # Streak deduction now happens at hydration, not here
        self.assertEqual(stack.players["attacker"].answer_streak, initial_streak)

    def test_overnight_steal_message_shows_projected_cost(self):
        manager, stack = _make_manager(self)
        result = manager.steal("attacker", "target", question_id=None)
        # Message should still mention the upcoming sacrifice
        self.assertIn("sacrifice", result.lower())

    def test_overnight_steal_sets_state_at_pretime(self):
        """State is set immediately at pre-load time for retaliation blocking."""
        manager, stack = _make_manager(self)
        manager.steal("attacker", "target", question_id=None)
        # Daily_state is mutated at pre-load time for retaliation blocking
        attacker_state = manager._get_daily_state("attacker")
        target_state = manager._get_daily_state("target")
        self.assertEqual(attacker_state.stealing_from, "target")
        self.assertIn("attacker", target_state.attacked_by)

    def test_overnight_steal_blocks_if_already_queued(self):
        manager, stack = _make_manager(self)
        stack.data_manager.log_powerup_usage("attacker", "steal_preload", "third", None)
        with self.assertRaises(PowerUpError) as cm:
            manager.steal("attacker", "target", question_id=None)
        self.assertIn("already have a powerup queued", str(cm.exception))
        self.assertEqual(len(stack.usages()), 1)

    def test_overnight_steal_blocks_duplicate_target(self):
        manager, stack = _make_manager(self)
        stack.data_manager.log_powerup_usage("third", "steal_preload", "target", None)
        with self.assertRaises(PowerUpError) as cm:
            manager.steal("attacker", "target", question_id=None)
        self.assertIn("already being targeted", str(cm.exception))
        self.assertEqual(len(stack.usages()), 1)


class TestHydration(unittest.TestCase):
    def test_hydrate_jinx_preload_sets_flags(self):
        manager, stack = _make_manager(self)
        stack.data_manager.log_powerup_usage("attacker", "jinx_preload", "target", None)
        next_day_id = stack.new_question_day()
        manager.hydrate_pending_powerups(question_id=next_day_id)
        self.assertTrue(manager._get_daily_state("attacker").silenced)
        self.assertEqual(manager._get_daily_state("target").jinxed_by, "attacker")
        # The queued row is promoted to the new question day
        self.assertEqual(
            stack.usages(), [("attacker", "jinx_preload", "target", next_day_id)]
        )

    def test_hydrate_steal_preload_sets_flags(self):
        manager, stack = _make_manager(self)
        stack.data_manager.log_powerup_usage(
            "attacker", "steal_preload", "target", None
        )
        next_day_id = stack.new_question_day()
        manager.hydrate_pending_powerups(question_id=next_day_id)
        state = manager._get_daily_state("attacker")
        self.assertEqual(state.stealing_from, "target")
        # Streak cost deducted at hydration time: 5 - 3 = 2
        self.assertEqual(stack.players["attacker"].answer_streak, 2)
        self.assertEqual(
            manager._get_daily_state("target").steal_attempt_by, "attacker"
        )
        self.assertEqual(
            stack.usages(), [("attacker", "steal_preload", "target", next_day_id)]
        )

    def test_hydrate_empty_pending_is_noop(self):
        manager, stack = _make_manager(self)
        manager.hydrate_pending_powerups(question_id=stack.new_question_day())
        # No state changes
        self.assertFalse(manager._get_daily_state("attacker").silenced)
        self.assertEqual(stack.usages(), [])
        self.assertEqual(stack.players["attacker"].answer_streak, 5)


# ---------------------------------------------------------------------------
# Feature B: Retroactive targeting
# ---------------------------------------------------------------------------


class TestRetroactiveJinx(unittest.TestCase):
    def _setup_with_answered_target(self, score_earned=100):
        """Set up a target that has already answered correctly with the given score."""
        manager, stack = _make_manager(self)
        target_state = manager._get_daily_state("target")
        target_state.is_correct = True
        target_state.score_earned = score_earned
        target_state.bonuses = {
            "streak": 20
        }  # streak stays with target in new mechanic
        return manager, stack

    def test_retro_jinx_transfers_share_of_score(self):
        """Retroactive jinx transfers 25% of target's total score_earned."""
        manager, stack = self._setup_with_answered_target(score_earned=100)
        manager.jinx("attacker", "target", question_id=stack.question_id)
        # 25% of 100 = 25 transferred
        self.assertEqual(stack.players["attacker"].score, 125)
        self.assertEqual(stack.players["target"].score, 75)

    def test_retro_jinx_silences_attacker(self):
        manager, stack = self._setup_with_answered_target(score_earned=100)
        manager.jinx("attacker", "target", question_id=stack.question_id)
        self.assertTrue(manager._get_daily_state("attacker").silenced)

    def test_retro_jinx_marks_target_jinxed_by(self):
        manager, stack = self._setup_with_answered_target(score_earned=100)
        manager.jinx("attacker", "target", question_id=stack.question_id)
        self.assertEqual(manager._get_daily_state("target").jinxed_by, "attacker")

    def test_retro_jinx_logs_normal_jinx_type(self):
        manager, stack = self._setup_with_answered_target(score_earned=100)
        manager.jinx("attacker", "target", question_id=stack.question_id)
        self.assertEqual(
            stack.usages(), [("attacker", "jinx", "target", stack.question_id)]
        )

    def test_retro_jinx_zero_score_no_transfer(self):
        """Retro jinx on target with 0 score_earned: no points transferred, no error.
        Link is still resolved (jinx_target cleared) to prevent double-transfer.
        """
        manager, stack = self._setup_with_answered_target(score_earned=0)
        manager.jinx("attacker", "target", question_id=stack.question_id)
        # No transfer; attacker is still silenced
        self.assertEqual(stack.players["attacker"].score, 100)
        self.assertEqual(stack.players["target"].score, 100)
        self.assertTrue(manager._get_daily_state("attacker").silenced)
        # Link is resolved - jinx_target cleared to prevent any future double-transfer
        self.assertIsNone(manager._get_daily_state("attacker").jinx_target)

    def test_retro_jinx_rounds_down(self):
        """int(7 * 0.25) = 1 (truncates, not rounds)."""
        manager, stack = self._setup_with_answered_target(score_earned=7)
        manager.jinx("attacker", "target", question_id=stack.question_id)
        self.assertEqual(stack.players["attacker"].score, 101)
        self.assertEqual(stack.players["target"].score, 99)

    def test_normal_jinx_not_triggered_when_target_unanswered(self):
        """Normal path: target hasn't answered, no immediate resolution."""
        manager, stack = _make_manager(self)
        manager.jinx("attacker", "target", question_id=stack.question_id)
        # No score changes yet
        self.assertEqual(stack.players["attacker"].score, 100)
        self.assertEqual(stack.players["target"].score, 100)
        self.assertEqual(manager._get_daily_state("target").jinxed_by, "attacker")

    def test_retro_jinx_triggered_after_on_guess(self):
        """Regression: on_guess must set is_correct so jinx sees it retroactively."""
        manager, stack = _make_manager(self)

        # Target answers correctly through the normal on_guess path
        manager.on_guess(
            GuessContext(
                player_id="target",
                player_name="Target",
                guess="answer",
                is_correct=True,
                points_earned=100,
                bonus_values={"streak": 20},
                question_id=stack.question_id,
            )
        )

        # Attacker jinxes after target has already answered
        result = manager.jinx("attacker", "target", question_id=stack.question_id)

        # Retroactive: 25% of 100 = 25 transferred
        self.assertEqual(stack.players["attacker"].score, 125)
        self.assertEqual(stack.players["target"].score, 75)
        self.assertIn("retroactive jinx", result)


class TestRetroactiveSteal(unittest.TestCase):
    def _setup_with_answered_target(self, target_bonuses=None):
        manager, stack = _make_manager(self)
        target_state = manager._get_daily_state("target")
        target_state.is_correct = True
        target_state.score_earned = 50
        target_state.bonuses = (
            target_bonuses if target_bonuses is not None else {"try": 20}
        )
        return manager, stack

    def test_retro_steal_deducts_higher_cost(self):
        manager, stack = self._setup_with_answered_target()
        manager.steal("attacker", "target", question_id=stack.question_id)
        # streak 5 - 5 (retro cost) = 0
        self.assertEqual(stack.players["attacker"].answer_streak, 0)

    def test_retro_steal_transfers_bonuses_immediately(self):
        manager, stack = self._setup_with_answered_target(target_bonuses={"try": 20})
        manager.steal("attacker", "target", question_id=stack.question_id)
        # try bonus of 20 transferred
        self.assertEqual(stack.players["attacker"].score, 120)
        self.assertEqual(stack.players["target"].score, 80)

    def test_retro_steal_nothing_to_steal(self):
        manager, stack = self._setup_with_answered_target(target_bonuses={})
        result = manager.steal("attacker", "target", question_id=stack.question_id)
        self.assertIn("nothing to steal", result)
        # No score changes
        self.assertEqual(stack.players["attacker"].score, 100)
        self.assertEqual(stack.players["target"].score, 100)

    def test_normal_steal_uses_lower_cost(self):
        """Normal path (target not answered): streak cost is STEAL_STREAK_COST."""
        manager, stack = _make_manager(self)
        manager.steal("attacker", "target", question_id=stack.question_id)
        # streak 5 - 3 = 2
        self.assertEqual(stack.players["attacker"].answer_streak, 2)

    def test_normal_steal_no_immediate_transfer(self):
        manager, stack = _make_manager(self)
        manager.steal("attacker", "target", question_id=stack.question_id)
        # No score change yet
        self.assertEqual(stack.players["attacker"].score, 100)
        self.assertEqual(stack.players["target"].score, 100)


# ---------------------------------------------------------------------------
# DailyGameSimulator — overnight and retroactive
# ---------------------------------------------------------------------------


def _make_question():
    return Question("Q?", "correct", "Test", 100)


def _ts(hour, minute=0):
    """Helper: datetime for today at given time."""
    return datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)


class TestSimulatorOvernightStealPreload(unittest.TestCase):
    """
    steal_preload: streak cost is applied by apply_steal at preload/hydration time.
    The snapshot captures the PRE-deduction streak; the simulator applies the
    cost as a negative streak_delta (same as a daytime steal).
    """

    def test_steal_preload_applies_streak_delta(self):
        """Thief's streak_delta should be -cost+1 after steal_preload + answering."""
        config = _make_config()
        # Snapshot streak = 5 (pre-deduction; cost=3 will be applied by apply_steal)
        attacker = Player(id="A", name="A", score=0, answer_streak=5)
        target = Player(id="T", name="T", score=0, answer_streak=3)
        initial_states = {"A": attacker, "T": target}

        events = [
            PowerUpEvent(_ts(2), "A", "steal_preload", "T"),
            GuessEvent(_ts(9), "T", "correct"),
            GuessEvent(_ts(9, 1), "A", "correct"),
        ]
        sim = DailyGameSimulator(
            _make_question(), ["correct"], None, events, initial_states, config
        )
        results = sim.run(apply_end_of_day=False)

        # apply_steal sets streak_delta=-3; answering adds +1 → net = -2
        self.assertEqual(results["A"]["streak_delta"], -2)

    def test_steal_preload_still_steals_bonuses(self):
        """Bonuses are still transferred when target answers after a steal_preload."""
        config = _make_config()
        # Snapshot streak = 5 (pre-deduction)
        attacker = Player(id="A", name="A", score=0, answer_streak=5)
        target = Player(id="T", name="T", score=0, answer_streak=3)
        initial_states = {"A": attacker, "T": target}

        events = [
            PowerUpEvent(_ts(2), "A", "steal_preload", "T"),
            GuessEvent(_ts(9), "T", "correct"),
        ]
        sim = DailyGameSimulator(
            _make_question(), ["correct"], None, events, initial_states, config
        )
        sim.run(apply_end_of_day=False)

        target_state = sim.daily_state["T"]
        attacker_state = sim.daily_state["A"]
        # Something should have been stolen (try bonus from first correct)
        total = target_state.score_earned + attacker_state.score_earned
        self.assertGreater(total, 0)
        # Attacker gained from steal
        self.assertGreater(attacker_state.score_earned, 0)


class TestSimulatorRetroactiveJinx(unittest.TestCase):
    def test_retro_jinx_transfers_share_immediately(self):
        """Retro jinx (target already answered) transfers 25% of score_earned at once."""
        config = _make_config()
        attacker = Player(id="A", name="A", score=0, answer_streak=1)
        target = Player(id="T", name="T", score=0, answer_streak=5)
        initial_states = {"A": attacker, "T": target}

        # Target answers at 9 AM, attacker jinxes at 9:30 AM (retroactive)
        events = [
            GuessEvent(_ts(9), "T", "correct"),
            PowerUpEvent(_ts(9, 30), "A", "jinx", "T"),
        ]
        sim = DailyGameSimulator(
            _make_question(), ["correct"], None, events, initial_states, config
        )
        results = sim.run(apply_end_of_day=False)

        attacker_state = sim.daily_state["A"]
        target_state = sim.daily_state["T"]

        # Retro transfer fires immediately: attacker gets positive score_earned
        self.assertGreater(attacker_state.score_earned, 0)
        # Streak bonus is NOT stripped from target by the new jinx
        self.assertIn("streak", target_state.bonuses)

    def test_forward_jinx_transfers_on_target_answer(self):
        """Forward jinx: transfer fires when the target answers, regardless of whether
        the attacker has answered. No dependency on attacker's answer.
        """
        config = _make_config()
        attacker = Player(id="A", name="A", score=0, answer_streak=1)
        target = Player(id="T", name="T", score=0, answer_streak=5)
        initial_states = {"A": attacker, "T": target}

        # Jinx fires BEFORE target answers; attacker never answers in this test
        events = [
            PowerUpEvent(_ts(8, 30), "A", "jinx", "T"),
            GuessEvent(_ts(9), "T", "correct"),
        ]
        sim = DailyGameSimulator(
            _make_question(), ["correct"], None, events, initial_states, config
        )
        sim.run(apply_end_of_day=False)

        attacker_state = sim.daily_state["A"]
        target_state = sim.daily_state["T"]

        # T: base=100, try_1=20, before_hint=10, fastest_1=10, streak(6)=25 = 165
        # Transfer: 25% of 165 = 41
        self.assertEqual(attacker_state.score_earned, 41)
        self.assertEqual(target_state.score_earned, 124)
        # Streak bonus stays with target (new jinx doesn't strip it)
        self.assertIn("streak", target_state.bonuses)
        # Jinx link is resolved (jinx_target cleared after transfer)
        self.assertIsNone(attacker_state.jinx_target)


class TestSimulatorRetroactiveSteal(unittest.TestCase):
    def test_retro_steal_higher_streak_cost(self):
        """Retroactive steal applies JBOT_RETRO_STEAL_STREAK_COST."""
        config = _make_config(steal_cost=3, retro_steal_cost=5)
        attacker = Player(id="A", name="A", score=0, answer_streak=6)
        target = Player(id="T", name="T", score=0, answer_streak=3)
        initial_states = {"A": attacker, "T": target}

        # Target answers, then attacker steals retroactively
        events = [
            GuessEvent(_ts(9), "T", "correct"),
            PowerUpEvent(_ts(9, 30), "A", "steal", "T"),
        ]
        sim = DailyGameSimulator(
            _make_question(), ["correct"], None, events, initial_states, config
        )
        sim.run(apply_end_of_day=False)

        attacker_state = sim.daily_state["A"]
        # Streak cost = retro cost of 5
        self.assertEqual(attacker_state.streak_delta, -5)

    def test_retro_steal_immediate_bonus_transfer(self):
        """Bonuses are transferred immediately when steal is retroactive."""
        config = _make_config()
        attacker = Player(id="A", name="A", score=0, answer_streak=6)
        target = Player(id="T", name="T", score=0, answer_streak=3)
        initial_states = {"A": attacker, "T": target}

        events = [
            GuessEvent(_ts(9), "T", "correct"),
            PowerUpEvent(_ts(9, 30), "A", "steal", "T"),
        ]
        sim = DailyGameSimulator(
            _make_question(), ["correct"], None, events, initial_states, config
        )
        sim.run(apply_end_of_day=False)

        attacker_state = sim.daily_state["A"]
        target_state = sim.daily_state["T"]
        total = attacker_state.score_earned + target_state.score_earned
        self.assertGreater(total, 0)
        self.assertGreater(attacker_state.score_earned, 0)


class TestSimulatorJinxPreload(unittest.TestCase):
    """jinx_preload simulator events: flags are set, no scores change."""

    ANSWER = "correct"

    def _make_simulator(self, initial_states, events):
        q = Question("Q?", self.ANSWER, "Test", 100)
        return DailyGameSimulator(
            q, [self.ANSWER], None, events, initial_states, _make_config()
        )

    def test_simulator_jinx_preload_sets_flags_only(self):
        """jinx_preload sets silenced/jinxed_by flags but earns no score."""
        attacker = Player(id="A", name="A", score=0, answer_streak=2)
        target = Player(id="T", name="T", score=0, answer_streak=5)
        events = [PowerUpEvent(_ts(2), "A", "jinx_preload", "T")]
        sim = self._make_simulator({"A": attacker, "T": target}, events)
        sim.run(apply_end_of_day=False)
        self.assertTrue(sim.daily_state["A"].silenced)
        self.assertEqual(sim.daily_state["T"].jinxed_by, "A")
        self.assertEqual(sim.daily_state["A"].score_earned, 0)
        self.assertEqual(sim.daily_state["T"].score_earned, 0)


# ---------------------------------------------------------------------------
# Simulator — REST event and rest_wakeup handling
# ---------------------------------------------------------------------------


class TestSimulatorRest(unittest.TestCase):
    """Simulator dispatches rest events correctly and skips rest_wakeup."""

    ANSWER = "correct"

    def _make_sim(self, initial_states, events):
        return DailyGameSimulator(
            _make_question(),
            [self.ANSWER],
            None,
            events,
            initial_states,
            _make_config(),
        )

    def test_rest_cancels_pending_jinx(self):
        """When target rests after a forward jinx, jinxed_by is cleared."""
        attacker = Player(id="A", name="A", score=0, answer_streak=2)
        target = Player(id="T", name="T", score=0, answer_streak=5)
        events = [
            PowerUpEvent(_ts(8), "A", "jinx", "T"),
            PowerUpEvent(_ts(9), "T", "rest", None),
        ]
        sim = self._make_sim({"A": attacker, "T": target}, events)
        sim.run(apply_end_of_day=False)
        self.assertIsNone(sim.daily_state["T"].jinxed_by)
        self.assertTrue(sim.daily_state["T"].is_resting)

    def test_rest_cancels_pending_steal(self):
        """When target rests after a forward steal, steal_attempt_by is cleared."""
        attacker = Player(id="A", name="A", score=0, answer_streak=4)
        target = Player(id="T", name="T", score=0, answer_streak=5)
        events = [
            PowerUpEvent(_ts(8), "A", "steal", "T"),
            PowerUpEvent(_ts(9), "T", "rest", None),
        ]
        sim = self._make_sim({"A": attacker, "T": target}, events)
        sim.run(apply_end_of_day=False)
        self.assertIsNone(sim.daily_state["T"].steal_attempt_by)
        self.assertTrue(sim.daily_state["T"].is_resting)

    def test_rest_wakeup_is_no_op(self):
        """rest_wakeup events are skipped — no bonus applied inside the simulator."""
        player = Player(id="P", name="P", score=0, answer_streak=2)
        events = [
            GuessEvent(_ts(9), "P", self.ANSWER),
            # rest_wakeup logged by live game; simulator must ignore it
            PowerUpEvent(_ts(9, 1), "P", "rest_wakeup", None),
        ]
        sim = self._make_sim({"P": player}, events)
        sim.run(apply_end_of_day=False)
        # No "rest" entry in simulator bonuses — multiplier is a DB concern, not replay
        self.assertNotIn("rest", sim.daily_state["P"].bonuses)
        # Score is correct (no double-application of any multiplier)
        self.assertTrue(sim.daily_state["P"].is_correct)


if __name__ == "__main__":
    unittest.main()
