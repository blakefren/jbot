"""
Tests for late-day jinx and steal — when the attacker has already answered correctly today.
"""

import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, call

from data.readers.question import Question
from src.core.daily_game_simulator import DailyGameSimulator
from src.core.events import GuessEvent, PowerUpEvent
from src.core.player import Player
from src.core.powerup import PowerUpError, PowerUpManager
from tests.src.core._powerup_helpers import make_config as _make_config


def _make_manager(players, today=None, return_today=True):
    """
    Build a PowerUpManager with mock dependencies.
    `players` is a dict {id: Player}.
    `return_today=True`  → attacker's last_correct is today (late-day mode).
    `return_today=False` → attacker's last_correct is yesterday (normal mode).
    """
    player_manager = MagicMock()
    data_manager = MagicMock()

    today = today or date.today()
    data_manager.get_today.return_value = today

    if return_today:
        data_manager.get_last_correct_guess_date.return_value = today
    else:
        data_manager.get_last_correct_guess_date.return_value = today - timedelta(
            days=1
        )

    player_manager.get_player.side_effect = lambda pid: players.get(pid)

    def update_score(pid, amount):
        if pid in players:
            players[pid].score += amount

    player_manager.update_score.side_effect = update_score

    def set_streak(pid, value):
        if pid in players:
            players[pid].answer_streak = value

    player_manager.set_streak.side_effect = set_streak

    config = _make_config()
    return (
        PowerUpManager(player_manager, data_manager, config),
        player_manager,
        data_manager,
    )


# ---------------------------------------------------------------------------
# Live-game tests — PowerUpManager
# ---------------------------------------------------------------------------


class TestJinxLateDay(unittest.TestCase):
    """Late-day jinx: attacker already answered correctly today."""

    def _setup(self):
        self.players = {
            "attacker": Player(id="attacker", name="A", score=200, answer_streak=3),
            "target": Player(id="target", name="T", score=150, answer_streak=5),
        }
        self.manager, self.pm, self.dm = _make_manager(self.players, return_today=True)
        # Attacker's in-memory state after answering today
        a_state = self.manager._get_daily_state("attacker")
        a_state.score_earned = 140
        a_state.bonuses = {"before_hint": 10, "fastest_1": 10, "streak": 15}
        # target hasn't answered yet by default
        return a_state

    def test_late_jinx_allowed(self):
        """Attacker who answered today can still use jinx — no error raised."""
        self._setup()
        result = self.manager.jinx("attacker", "target", question_id=99)
        self.assertIsNotNone(result)

    def test_late_jinx_strips_before_hint(self):
        """before_hint bonus is removed from attacker's score."""
        a_state = self._setup()
        self.manager.jinx("attacker", "target", question_id=99)
        self.assertNotIn("before_hint", a_state.bonuses)

    def test_late_jinx_strips_fastest(self):
        """fastest_* bonuses are removed from attacker's score."""
        a_state = self._setup()
        self.manager.jinx("attacker", "target", question_id=99)
        self.assertNotIn("fastest_1", a_state.bonuses)
        # fastest alias also cleared
        self.assertNotIn("fastest", a_state.bonuses)

    def test_late_jinx_deducts_cost_from_score(self):
        """Attacker's score is reduced by stripped bonus total (before_hint + fastest)."""
        self._setup()
        initial_score = self.players["attacker"].score  # 200
        self.manager.jinx("attacker", "target", question_id=99)
        # before_hint=10, fastest_1=10 → cost 20
        self.assertEqual(self.players["attacker"].score, initial_score - 20)

    def test_late_jinx_no_cost_when_no_bonuses(self):
        """If attacker has no strippable bonuses, no score change occurs."""
        self._setup()
        a_state = self.manager._get_daily_state("attacker")
        a_state.bonuses = {"streak": 15}  # only streak, not strippable by jinx
        initial_score = self.players["attacker"].score
        self.manager.jinx("attacker", "target", question_id=99)
        self.assertEqual(self.players["attacker"].score, initial_score)

    def test_late_jinx_logs_jinx_late_type(self):
        """DB records 'jinx_late' for this variant."""
        self._setup()
        self.manager.jinx("attacker", "target", question_id=99)
        self.dm.log_powerup_usage.assert_called_once_with(
            "attacker", "jinx_late", "target", 99
        )

    def test_late_jinx_attacker_silenced(self):
        """Attacker is marked silenced (for consistency) even in late-day path."""
        a_state = self._setup()
        self.manager.jinx("attacker", "target", question_id=99)
        self.assertTrue(a_state.silenced)

    def test_late_jinx_forward_sets_jinxed_by_on_target(self):
        """When target hasn't answered yet, target.jinxed_by is set."""
        self._setup()
        self.manager.jinx("attacker", "target", question_id=99)
        t_state = self.manager._get_daily_state("target")
        self.assertEqual(t_state.jinxed_by, "attacker")

    def test_late_jinx_retro_transfers_half_streak(self):
        """When target already answered with streak bonus, half is transferred."""
        self._setup()
        t_state = self.manager._get_daily_state("target")
        t_state.is_correct = True
        t_state.bonuses = {"streak": 20}

        initial_attacker = self.players["attacker"].score  # 200
        initial_target = self.players["target"].score  # 150

        self.manager.jinx("attacker", "target", question_id=99)

        # half = int(20 * 0.5) = 10 transferred; plus attacker's own cost of 20
        expected_attacker = initial_attacker - 20 + 10  # -20 cost, +10 steal
        self.assertEqual(self.players["attacker"].score, expected_attacker)
        self.assertEqual(self.players["target"].score, initial_target - 10)

    def test_late_jinx_retro_no_streak_blocked(self):
        """When target answered but has no streak bonus, jinx is blocked entirely."""
        self._setup()
        t_state = self.manager._get_daily_state("target")
        t_state.is_correct = True
        t_state.bonuses = {}

        initial_attacker = self.players["attacker"].score
        with self.assertRaises(PowerUpError):
            self.manager.jinx("attacker", "target", question_id=99)
        # No costs paid, no changes
        self.assertEqual(self.players["attacker"].score, initial_attacker)

    def test_powerup_used_today_blocks_second_jinx(self):
        """A second jinx attempt by the same attacker is blocked."""
        self._setup()
        self.manager.jinx("attacker", "target", question_id=99)
        with self.assertRaises(PowerUpError):
            self.manager.jinx("attacker", "target", question_id=99)

    def test_normal_jinx_still_blocked_after_answer(self):
        """Regression: the normal path still works correctly for non-late-day."""
        self.players = {
            "attacker": Player(id="attacker", name="A", score=200, answer_streak=3),
            "target": Player(id="target", name="T", score=150, answer_streak=5),
        }
        self.manager, self.pm, self.dm = _make_manager(self.players, return_today=False)
        result = self.manager.jinx("attacker", "target", question_id=1)
        # Normal path → logs 'jinx', not 'jinx_late'
        self.dm.log_powerup_usage.assert_called_once_with(
            "attacker", "jinx", "target", 1
        )
        self.assertIn("hint", result)

    def test_late_jinx_bonuses_not_refunded_when_target_rests(self):
        """Bonuses stripped as the late-jinx cost are not restored when the target rests."""
        today = date.today()
        players = {
            "attacker": Player(id="attacker", name="A", score=200, answer_streak=3),
            "target": Player(id="target", name="T", score=150, answer_streak=5),
        }
        manager, _pm, dm = _make_manager(players, return_today=False)
        dm.get_last_correct_guess_date.side_effect = lambda pid: (
            today if pid == "attacker" else today - timedelta(days=1)
        )
        a_state = manager._get_daily_state("attacker")
        a_state.is_correct = True
        a_state.score_earned = 140
        a_state.bonuses = {"before_hint": 10, "fastest_1": 10, "streak": 15}
        manager.jinx("attacker", "target", question_id=99)
        score_after_jinx = players["attacker"].score
        manager.rest("target", 99, "Ans")
        self.assertIsNone(manager._get_daily_state("target").jinxed_by)
        self.assertEqual(players["attacker"].score, score_after_jinx)

    def test_late_jinx_forward_target_never_answers_cost_not_refunded(self):
        """Late-day forward jinx where target never answers: stripped bonuses are forfeit."""
        a_state = self._setup()
        initial_attacker = self.players["attacker"].score  # 200
        self.manager.jinx("attacker", "target", question_id=99)
        score_after_jinx = self.players["attacker"].score  # 200 - 20 = 180

        # Target never answers — no on_guess call for target
        # Attacker's score must remain at the post-jinx value (cost is permanent)
        self.assertEqual(self.players["attacker"].score, score_after_jinx)
        self.assertLess(score_after_jinx, initial_attacker)
        # Jinx flag stayed set on target (never resolved)
        self.assertEqual(self.manager._get_daily_state("target").jinxed_by, "attacker")


class TestStealLateDay(unittest.TestCase):
    """Late-day steal: thief already answered correctly today."""

    def _setup(self, thief_streak=5, thief_bonuses=None):
        self.players = {
            "thief": Player(
                id="thief", name="T", score=300, answer_streak=thief_streak
            ),
            "target": Player(id="target", name="V", score=200, answer_streak=4),
        }
        self.manager, self.pm, self.dm = _make_manager(self.players, return_today=True)
        t_state = self.manager._get_daily_state("thief")
        t_state.is_correct = (
            True  # thief has answered correctly today (late-day scenario)
        )
        t_state.score_earned = 200
        # Default bonuses use streak=5 after answering → streak_length=6 → bonus=25 (capped)
        t_state.bonuses = thief_bonuses if thief_bonuses is not None else {"streak": 25}
        return t_state

    def test_late_steal_allowed(self):
        """Thief who answered today can still use steal — no error raised."""
        self._setup()
        self.manager.steal("thief", "target", question_id=1)

    def test_late_steal_forward_recalculates_streak_bonus(self):
        """Forward steal (target not yet answered) recalculates thief's streak bonus.

        thief streak=5 → effective streak after answering=6, bonus=25 (capped).
        Forward cost=3 → effective-cost=3, new_bonus=15. Delta=10 deducted.
        set_streak uses initial-cost=2 (stored value for future days).
        """
        t_state = self._setup(thief_streak=5, thief_bonuses={"streak": 25})
        initial_score = self.players["thief"].score  # 300

        self.manager.steal("thief", "target", question_id=1)

        # streak cost: new stored = max(0, 5 - 3) = 2, set_streak called with 2
        self.pm.set_streak.assert_called_once_with("thief", 2)
        # bonus uses effective-cost formula: effective=6, new_bonus_streak=6-3=3, bonus=15
        new_bonus = 15  # min(3*5, 25)
        expected_score = initial_score - (25 - new_bonus)
        self.assertEqual(self.players["thief"].score, expected_score)
        self.assertEqual(t_state.bonuses.get("streak"), new_bonus)

    def test_late_steal_retro_recalculates_streak_bonus(self):
        """Retro steal (target already answered) recalculates thief's streak bonus.

        thief streak=5 → after answering=6, bonus=25 (capped).
        Retro cost=5 → new_streak=1, new_bonus=0. Delta=25 deducted.
        """
        t_state = self._setup(thief_streak=5, thief_bonuses={"streak": 25})
        # target already answered
        tgt_state = self.manager._get_daily_state("target")
        tgt_state.is_correct = True
        tgt_state.bonuses = {"before_hint": 10}  # stealable
        initial_score = self.players["thief"].score  # 300

        self.manager.steal("thief", "target", question_id=1)

        # retro cost 5: new_streak = max(0, 5 - 5) = 0 → bonus = 0
        self.pm.set_streak.assert_called_once_with("thief", 0)
        self.assertEqual(self.players["thief"].score, initial_score - 25 + 10)
        self.assertNotIn("streak", t_state.bonuses)

    def test_late_steal_zero_streak_rejected(self):
        """Steal is rejected when thief has zero streak days (nothing to sacrifice)."""
        t_state = self._setup(thief_streak=0, thief_bonuses={})
        with self.assertRaises(PowerUpError) as cm:
            self.manager.steal("thief", "target", question_id=1)
        self.assertIn("streak days", str(cm.exception))

    def test_late_steal_normal_path_unchanged_without_bonuses(self):
        """When thief has no streak bonus, no bonus recalculation side-effects occur."""
        # thief streak=1 → bonus would be 0 anyway
        t_state = self._setup(thief_streak=1, thief_bonuses={})
        initial_score = self.players["thief"].score
        self.manager.steal("thief", "target", question_id=1)
        # streak cost: new = max(0, 1-3) = 0, set_streak called
        self.pm.set_streak.assert_called_once_with("thief", 0)
        # No score change for streak delta (both bonuses 0)
        self.pm.update_score.assert_not_called()

    def test_late_steal_after_jinx_took_streak_no_recalculation(self):
        """When thief was jinxed and their streak bonus was already transferred away,
        a subsequent late steal must NOT add a new streak bonus to the thief's score.

        Regression: recalculate_streak_bonus previously read old_bonus=0 (key absent
        because jinx popped it) and added new_bonus as a full positive delta.
        """
        # thief streak=5 → answered → streak bonus=25, then jinx popped it
        t_state = self._setup(thief_streak=5, thief_bonuses={})
        # Simulate jinx having already transferred the streak bonus away:
        # bonuses dict has no "streak" key (popped), score_earned reflects the loss.
        t_state.jinxed_by = "jinxer"
        initial_score = self.players["thief"].score

        self.manager.steal("thief", "target", question_id=1)

        # Streak days should still be deducted
        self.pm.set_streak.assert_called_once_with("thief", 2)  # 5 - 3
        # No score adjustment for streak bonus — jinx already owns it
        self.pm.update_score.assert_not_called()
        self.assertEqual(self.players["thief"].score, initial_score)
        self.assertNotIn("streak", t_state.bonuses)


# ---------------------------------------------------------------------------
# Simulator tests — DailyGameSimulator
# ---------------------------------------------------------------------------


class TestSimulatorJinxLate(unittest.TestCase):
    """Simulator handles jinx_late events correctly."""

    ANSWER = "apple"

    def _make_simulator(self, initial_states, events):
        question = Question(
            question="Q?", answer=self.ANSWER, category="Test", clue_value=100
        )
        config = _make_config()
        return DailyGameSimulator(
            question=question,
            answers=[self.ANSWER],
            hint_timestamp="2023-01-01 12:00:00",
            events=events,
            initial_player_states=initial_states,
            config=config,
        )

    def test_jinx_late_strips_before_hint_from_attacker(self):
        """jinx_late event strips attacker's before_hint and fastest bonuses."""
        initial_states = {
            "A": Player(id="A", name="Attacker", score=100, answer_streak=2),
            "T": Player(id="T", name="Target", score=100, answer_streak=0),
        }
        events = [
            # Attacker answers first (before hint)
            GuessEvent(
                timestamp="2023-01-01 10:00:00",
                user_id="A",
                guess_text=self.ANSWER,
            ),
            # Target answers
            GuessEvent(
                timestamp="2023-01-01 10:05:00",
                user_id="T",
                guess_text=self.ANSWER,
            ),
            # Attacker then jinxes (late-day)
            PowerUpEvent(
                timestamp="2023-01-01 10:10:00",
                user_id="A",
                powerup_type="jinx_late",
                target_user_id="T",
            ),
        ]
        sim = self._make_simulator(initial_states, events)
        results = sim.run()

        # Attacker scored: base=100, first_try=20, before_hint=10, fastest=10, streak(3)=15 → 155
        # jinx_late strips before_hint=10 and fastest=10 → 155 - 20 = 135
        # Target not yet answered when jinx fires (order: T answers then jinx fires on T who IS answered)
        # Wait - T answered before jinx, so target IS already correct → retro path
        # T streak=0 → no streak bonus → no transfer
        self.assertEqual(results["A"]["score_earned"], 155 - 20)

    def test_jinx_late_forward_target_not_answered_sets_jinx(self):
        """jinx_late on a target who hasn't answered yet sets their jinxed_by."""
        initial_states = {
            "A": Player(id="A", name="Attacker", score=100, answer_streak=2),
            "T": Player(id="T", name="Target", score=100, answer_streak=5),
        }
        events = [
            # Attacker answers
            GuessEvent(
                timestamp="2023-01-01 10:00:00",
                user_id="A",
                guess_text=self.ANSWER,
            ),
            # Attacker uses late jinx on T (T hasn't answered yet)
            PowerUpEvent(
                timestamp="2023-01-01 10:05:00",
                user_id="A",
                powerup_type="jinx_late",
                target_user_id="T",
            ),
            # T answers after being jinxed — streak bonus should be lost
            GuessEvent(
                timestamp="2023-01-01 10:10:00",
                user_id="T",
                guess_text=self.ANSWER,
            ),
        ]
        sim = self._make_simulator(initial_states, events)
        results = sim.run()

        # T streak=5 → streak_length=6 → bonus=25. Jinxed → loses streak bonus.
        self.assertNotIn("streak", sim.daily_state["T"].bonuses)

    def test_jinx_late_retro_transfers_half_streak_to_attacker(self):
        """jinx_late with target already answered transfers half streak bonus."""
        initial_states = {
            "A": Player(id="A", name="Attacker", score=100, answer_streak=2),
            "T": Player(id="T", name="Target", score=100, answer_streak=6),
        }
        events = [
            # Target answers first
            GuessEvent(
                timestamp="2023-01-01 10:00:00",
                user_id="T",
                guess_text=self.ANSWER,
            ),
            # Attacker answers
            GuessEvent(
                timestamp="2023-01-01 10:05:00",
                user_id="A",
                guess_text=self.ANSWER,
            ),
            # Attacker uses late jinx on T (already answered)
            PowerUpEvent(
                timestamp="2023-01-01 10:10:00",
                user_id="A",
                powerup_type="jinx_late",
                target_user_id="T",
            ),
        ]
        sim = self._make_simulator(initial_states, events)
        results = sim.run()

        # T streak=6 → streak_length=7 → bonus = min(35, 25) = 25
        # jinx_late retro: half = int(25 * 0.5) = 12 transferred
        # T loses 12 from score_earned
        self.assertNotIn("streak", sim.daily_state["T"].bonuses)

        # A: base=100, try1=20, before_hint=10, fastest_2=5 (T was 1st), streak(3)=15 → 150
        # jinx_late strips before_hint=10 + fastest_2=5 = 15 cost, gains 12 from T → 150-15+12=147
        self.assertEqual(results["A"]["score_earned"], 147)


class TestSimulatorStealLateDay(unittest.TestCase):
    """Simulator handles steal events after attacker has already answered."""

    ANSWER = "apple"

    def _make_simulator(self, initial_states, events):
        question = Question(
            question="Q?", answer=self.ANSWER, category="Test", clue_value=100
        )
        config = _make_config()
        return DailyGameSimulator(
            question=question,
            answers=[self.ANSWER],
            hint_timestamp="2023-01-01 12:00:00",
            events=events,
            initial_player_states=initial_states,
            config=config,
        )

    def test_steal_late_retro_overrides_streak_delta(self):
        """Late-day retro steal overrides the +1 streak_delta from answering.

        Thief streak=5 answers → streak_delta=1, effective=6.
        Retro cost=5 → new_streak=1. streak_delta should be 1-5 = -4.
        Final streak = 5 + (-4) = 1.
        """
        initial_states = {
            "thief": Player(id="thief", name="Thief", score=100, answer_streak=5),
            "target": Player(id="target", name="Target", score=100, answer_streak=3),
        }
        events = [
            # Target answers first
            GuessEvent(
                timestamp="2023-01-01 10:00:00",
                user_id="target",
                guess_text=self.ANSWER,
            ),
            # Thief answers
            GuessEvent(
                timestamp="2023-01-01 10:05:00",
                user_id="thief",
                guess_text=self.ANSWER,
            ),
            # Thief steals from target who already answered (retro steal, late-day)
            PowerUpEvent(
                timestamp="2023-01-01 10:10:00",
                user_id="thief",
                powerup_type="steal",
                target_user_id="target",
            ),
        ]
        sim = self._make_simulator(initial_states, events)
        results = sim.run()

        # Final streak for thief: 5 (initial) + (-4) (from -5 cost +1 answer) = 1
        self.assertEqual(results["thief"]["final_streak"], 1)

    def test_steal_late_retro_recalculates_streak_bonus(self):
        """Late-day retro steal recalculates streak bonus for thief.

        Thief streak=5 → after answer=6, bonus=25 (capped).
        Retro cost=5 → new_streak=1, new_bonus=0. Score adjusted by -25.
        """
        initial_states = {
            "thief": Player(id="thief", name="Thief", score=100, answer_streak=5),
            "target": Player(id="target", name="Target", score=100, answer_streak=0),
        }
        events = [
            GuessEvent(
                timestamp="2023-01-01 10:00:00",
                user_id="target",
                guess_text=self.ANSWER,
            ),
            GuessEvent(
                timestamp="2023-01-01 10:05:00",
                user_id="thief",
                guess_text=self.ANSWER,
            ),
            PowerUpEvent(
                timestamp="2023-01-01 10:10:00",
                user_id="thief",
                powerup_type="steal",
                target_user_id="target",
            ),
        ]
        sim = self._make_simulator(initial_states, events)
        results = sim.run()

        # Verify streak was properly adjusted and bonus removed
        self.assertEqual(results["thief"]["final_streak"], 1)
        self.assertNotIn("streak", sim.daily_state["thief"].bonuses)

    def test_steal_late_forward_overrides_streak_delta(self):
        """Late-day forward steal overrides streak_delta from answering.

        Thief streak=5 answers → streak_delta=1, effective=6.
        Forward cost=3 → new_streak=3. streak_delta = 3-5 = -2.
        Final streak = 5 + (-2) = 3.
        """
        initial_states = {
            "thief": Player(id="thief", name="Thief", score=100, answer_streak=5),
            "target": Player(id="target", name="Target", score=100, answer_streak=3),
        }
        events = [
            # Thief answers first this time
            GuessEvent(
                timestamp="2023-01-01 10:00:00",
                user_id="thief",
                guess_text=self.ANSWER,
            ),
            # Thief steals from target who hasn't answered yet (forward steal, late-day)
            PowerUpEvent(
                timestamp="2023-01-01 10:05:00",
                user_id="thief",
                powerup_type="steal",
                target_user_id="target",
            ),
            # Target answers after steal is set up — steal resolves
            GuessEvent(
                timestamp="2023-01-01 10:10:00",
                user_id="target",
                guess_text=self.ANSWER,
            ),
        ]
        sim = self._make_simulator(initial_states, events)
        results = sim.run()

        # Final streak for thief: 5 (initial) + (-2) = 3
        self.assertEqual(results["thief"]["final_streak"], 3)

    def test_steal_symmetry_early_vs_late_target_never_answers(self):
        """Attacker-timing symmetry: early-forward and late-forward steal yield the same
        net streak-related score when the target never answers.

        Early path: thief steals (streak 5→2), then answers (streak_len=3, bonus=15).
        Late path:  thief answers (streak_len=6, bonus=25), then steals (bonus revised to 15).
        Both should produce score_earned = base + bonuses_with_streak_of_15.
        """
        ANSWER = self.ANSWER
        # Both thieves answer after the hint (no before_hint bonus) and are first correct.
        hint_ts = "2023-01-01 12:00:00"
        answer_ts = "2023-01-01 13:00:00"  # after hint
        steal_early_ts = "2023-01-01 09:00:00"  # before answer
        steal_late_ts = "2023-01-01 14:00:00"  # after answer

        question = Question(
            question="Q?", answer=ANSWER, category="Test", clue_value=100
        )
        config = _make_config()

        # --- Early steal path ---
        early_initial = {
            "thief": Player(id="thief", name="T", score=0, answer_streak=5),
            "target": Player(id="target", name="V", score=0, answer_streak=3),
        }
        early_events = [
            PowerUpEvent(steal_early_ts, "thief", "steal", "target"),
            GuessEvent(answer_ts, "thief", ANSWER),
            # target never answers
        ]
        early_sim = DailyGameSimulator(
            question, [ANSWER], hint_ts, early_events, early_initial, config
        )
        early_results = early_sim.run(apply_end_of_day=False)

        # --- Late steal path ---
        late_initial = {
            "thief": Player(id="thief", name="T", score=0, answer_streak=5),
            "target": Player(id="target", name="V", score=0, answer_streak=3),
        }
        late_events = [
            GuessEvent(answer_ts, "thief", ANSWER),
            PowerUpEvent(steal_late_ts, "thief", "steal", "target"),
            # target never answers
        ]
        late_sim = DailyGameSimulator(
            question, [ANSWER], hint_ts, late_events, late_initial, config
        )
        late_results = late_sim.run(apply_end_of_day=False)

        # Both paths must yield identical thief score_earned (symmetry principle)
        self.assertEqual(
            early_results["thief"]["score_earned"],
            late_results["thief"]["score_earned"],
            f"Symmetry broken: early={early_results['thief']['score_earned']} "
            f"late={late_results['thief']['score_earned']}",
        )

    def test_steal_late_forward_recalculates_streak_bonus(self):
        """Late-day forward steal recalculates streak bonus for thief.

        Thief streak=5 → streak_length=6, bonus=25 (capped).
        Forward cost=3 → new_streak=3, new_bonus=15. Score adjusted by -10.
        """
        initial_states = {
            "thief": Player(id="thief", name="Thief", score=100, answer_streak=5),
            "target": Player(id="target", name="Target", score=100, answer_streak=3),
        }
        events = [
            GuessEvent(
                timestamp="2023-01-01 10:00:00",
                user_id="thief",
                guess_text=self.ANSWER,
            ),
            PowerUpEvent(
                timestamp="2023-01-01 10:05:00",
                user_id="thief",
                powerup_type="steal",
                target_user_id="target",
            ),
            GuessEvent(
                timestamp="2023-01-01 10:10:00",
                user_id="target",
                guess_text=self.ANSWER,
            ),
        ]
        sim = self._make_simulator(initial_states, events)
        results = sim.run()

        # After bonus recalc: new_streak=3, new_bonus=15
        self.assertEqual(sim.daily_state["thief"].bonuses.get("streak"), 15)
        self.assertEqual(results["thief"]["final_streak"], 3)


class TestStealThenLateJinxNoDoubleDeduction(unittest.TestCase):
    """Regression: bonuses already stolen from a player must not be deducted
    again when that same player later uses a late-day jinx."""

    ANSWER = "apple"

    def _make_simulator(self, initial_states, events):
        question = Question(
            question="Q?", answer=self.ANSWER, category="Test", clue_value=100
        )
        config = _make_config()
        return DailyGameSimulator(
            question=question,
            answers=[self.ANSWER],
            hint_timestamp="2023-01-01 12:00:00",
            events=events,
            initial_player_states=initial_states,
            config=config,
        )

    def test_steal_target_then_late_jinx_no_double_deduction(self):
        """A is targeted by steal from T. A answers correctly — T steals A's
        try/before_hint/fastest bonuses. A then uses a late-day jinx on B.
        The bonuses already transferred to T must NOT be deducted again as
        the late-jinx cost.

        A scoring:
          base=100, try_1=20, first_try(alias), before_hint=10, fastest_2=5, streak(3)=15 → 150
          Steal by T: -(20+10+5)=35 → 115 (try/before_hint/fastest removed from bonuses)
          Late-jinx cost: before_hint+fastest already gone → 0  (was -15 before fix)
          Retro jinx on B (B streak_length=1 < 2 → bonus=0): no transfer
          Final A score_earned = 115

        Without the fix, the jinx cost would re-deduct before_hint(10)+fastest_2(5)=15,
        leaving A at 100.
        """
        initial_states = {
            "B": Player(id="B", name="B", score=100, answer_streak=0),
            "A": Player(id="A", name="A", score=100, answer_streak=2),
            "T": Player(
                id="T", name="T", score=100, answer_streak=3
            ),  # needs ≥1 streak to steal
        }
        events = [
            # B answers first (fastest_1, before hint)
            GuessEvent(
                timestamp="2023-01-01 09:00:00",
                user_id="B",
                guess_text=self.ANSWER,
            ),
            # T steals from A before A has answered
            PowerUpEvent(
                timestamp="2023-01-01 09:05:00",
                user_id="T",
                powerup_type="steal",
                target_user_id="A",
            ),
            # A answers (before hint, second fastest) → steal resolves, bonuses transferred to T
            GuessEvent(
                timestamp="2023-01-01 09:10:00",
                user_id="A",
                guess_text=self.ANSWER,
            ),
            # A uses a late-day jinx on B (A already answered → late-day path)
            PowerUpEvent(
                timestamp="2023-01-01 09:15:00",
                user_id="A",
                powerup_type="jinx_late",
                target_user_id="B",
            ),
        ]
        sim = self._make_simulator(initial_states, events)
        results = sim.run()

        # Stealable bonuses must be gone from A's bonus dict after steal resolved
        a_bonuses = sim.daily_state["A"].bonuses
        self.assertNotIn("before_hint", a_bonuses)
        self.assertNotIn("fastest_1", a_bonuses)
        self.assertNotIn("fastest_2", a_bonuses)

        # A's final score: 115 (after steal, no double-deduction from jinx cost).
        # Without the fix this would be 100 (jinx cost re-deducts already-stolen bonuses).
        self.assertEqual(results["A"]["score_earned"], 115)

    def test_early_and_late_steal_same_net_cost(self):
        """Early and late forward steal both result in the same thief streak after the steal."""
        streak = 5
        # Early steal: thief has NOT answered yet
        early_players = {
            "thief": Player(id="thief", name="T", score=300, answer_streak=streak),
            "target": Player(id="target", name="V", score=200, answer_streak=4),
        }
        early_manager, _, _ = _make_manager(early_players, return_today=False)
        early_manager.steal("thief", "target", question_id=1)
        early_streak = early_players["thief"].answer_streak

        # Late steal: thief HAS answered already today
        late_players = {
            "thief": Player(id="thief", name="T", score=300, answer_streak=streak),
            "target": Player(id="target", name="V", score=200, answer_streak=4),
        }
        late_manager, _, _ = _make_manager(late_players, return_today=True)
        thief_state = late_manager._get_daily_state("thief")
        thief_state.is_correct = True
        thief_state.score_earned = 200
        thief_state.bonuses = {"streak": 25}
        late_manager.steal("thief", "target", question_id=1)
        late_streak = late_players["thief"].answer_streak

        self.assertEqual(early_streak, late_streak)


if __name__ == "__main__":
    unittest.main()
