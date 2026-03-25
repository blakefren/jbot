"""
Tests for overnight powerup pre-loading (Feature A) and retroactive targeting (Feature B).
"""

import unittest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

from src.core.daily_game_simulator import DailyGameSimulator
from src.core.events import GuessEvent, PowerUpEvent
from src.core.player import Player
from src.core.powerup import PowerUpError, PowerUpManager
from src.core.state import DailyPlayerState


def _make_config(
    steal_cost=3,
    retro_steal_cost=5,
    retro_jinx_ratio=0.5,
):
    cfg = MagicMock()

    def _get(key, default=None):
        return {
            "JBOT_STEAL_STREAK_COST": str(steal_cost),
            "JBOT_RETRO_STEAL_STREAK_COST": str(retro_steal_cost),
            "JBOT_RETRO_JINX_BONUS_RATIO": str(retro_jinx_ratio),
            "JBOT_BONUS_STREAK_PER_DAY": "5",
            "JBOT_BONUS_STREAK_CAP": "25",
            "JBOT_BONUS_BEFORE_HINT": "10",
            "JBOT_BONUS_FASTEST_CSV": "10,5,1",
            "JBOT_BONUS_TRY_CSV": "20,10,5",
            "JBOT_REST_MULTIPLIER": "1.2",
            "JBOT_EMOJI_FASTEST": "🥇",
            "JBOT_EMOJI_FASTEST_CSV": "🥇,🥈,🥉",
            "JBOT_EMOJI_FIRST_TRY": "🎯",
            "JBOT_EMOJI_STREAK": "🔥",
            "JBOT_EMOJI_BEFORE_HINT": "🧠",
            "JBOT_EMOJI_JINXED": "🥶",
            "JBOT_EMOJI_SILENCED": "🤐",
            "JBOT_EMOJI_STOLEN_FROM": "💸",
            "JBOT_EMOJI_STEALING": "💰",
            "JBOT_EMOJI_REST": "😴",
            "JBOT_EMOJI_REST_WAKEUP": "⏰",
        }.get(key, default)

    cfg.get.side_effect = _get
    return cfg


def _make_manager(players=None):
    """Build a PowerUpManager with mocked dependencies."""
    player_manager = MagicMock()
    data_manager = MagicMock()

    if players is None:
        players = {
            "attacker": Player(
                id="attacker", name="Attacker", score=100, answer_streak=5
            ),
            "target": Player(id="target", name="Target", score=100, answer_streak=4),
        }

    player_manager.get_player.side_effect = lambda pid: players.get(pid)

    def _update_score(pid, amount):
        if pid in players:
            players[pid].score += amount

    def _set_streak(pid, val):
        if pid in players:
            players[pid].answer_streak = val

    player_manager.update_score.side_effect = _update_score
    player_manager.set_streak.side_effect = _set_streak

    data_manager.get_last_correct_guess_date.return_value = date.today() - timedelta(
        days=1
    )
    data_manager.get_today.return_value = date.today()

    # No pending powerups by default
    data_manager.get_pending_powerup.return_value = None
    data_manager.get_pending_powerup_for_target.return_value = None

    return (
        PowerUpManager(player_manager, data_manager, _make_config()),
        player_manager,
        data_manager,
        players,
    )


# ---------------------------------------------------------------------------
# Feature A: Overnight pre-loading
# ---------------------------------------------------------------------------


class TestOvernightJinx(unittest.TestCase):
    def test_overnight_jinx_logs_preload_type(self):
        manager, pm, dm, players = _make_manager()
        result = manager.jinx("attacker", "target", question_id=None)
        dm.log_powerup_usage.assert_called_once_with(
            "attacker", "jinx_preload", "target", None
        )
        self.assertIn("queued for tomorrow", result)

    def test_overnight_jinx_silences_attacker_immediately(self):
        manager, pm, dm, players = _make_manager()
        manager.jinx("attacker", "target", question_id=None)
        self.assertTrue(manager._get_daily_state("attacker").silenced)

    def test_overnight_jinx_blocks_if_already_queued(self):
        manager, pm, dm, players = _make_manager()
        dm.get_pending_powerup.return_value = {"id": 1, "powerup_type": "jinx_preload"}
        with self.assertRaises(PowerUpError) as cm:
            manager.jinx("attacker", "target", question_id=None)
        self.assertIn("already have a powerup queued", str(cm.exception))

    def test_overnight_jinx_blocks_duplicate_target(self):
        manager, pm, dm, players = _make_manager()
        dm.get_pending_powerup_for_target.return_value = {
            "id": 2,
            "powerup_type": "jinx_preload",
        }
        with self.assertRaises(PowerUpError) as cm:
            manager.jinx("attacker", "target", question_id=None)
        self.assertIn("already being targeted", str(cm.exception))


class TestOvernightSteal(unittest.TestCase):
    def test_overnight_steal_logs_preload_type(self):
        manager, pm, dm, players = _make_manager()
        manager.steal("attacker", "target", question_id=None)
        dm.log_powerup_usage.assert_called_once_with(
            "attacker", "steal_preload", "target", None
        )

    def test_overnight_steal_does_not_deduct_streak_immediately(self):
        manager, pm, dm, players = _make_manager()
        initial_streak = players["attacker"].answer_streak  # 5
        manager.steal("attacker", "target", question_id=None)
        # Streak deduction now happens at hydration, not here
        self.assertEqual(players["attacker"].answer_streak, initial_streak)

    def test_overnight_steal_message_shows_projected_cost(self):
        manager, pm, dm, players = _make_manager()
        result = manager.steal("attacker", "target", question_id=None)
        # Message should still mention the upcoming sacrifice
        self.assertIn("sacrifice", result.lower())

    def test_overnight_steal_sets_no_state_at_pretime(self):
        """State is set during hydration, not at pre-load time."""
        manager, pm, dm, players = _make_manager()
        manager.steal("attacker", "target", question_id=None)
        # No daily_state mutation at pre-load time
        self.assertIsNone(manager._get_daily_state("attacker").stealing_from)

    def test_overnight_steal_blocks_if_already_queued(self):
        manager, pm, dm, players = _make_manager()
        dm.get_pending_powerup.return_value = {"id": 1, "powerup_type": "steal_preload"}
        with self.assertRaises(PowerUpError) as cm:
            manager.steal("attacker", "target", question_id=None)
        self.assertIn("already have a powerup queued", str(cm.exception))

    def test_overnight_steal_blocks_duplicate_target(self):
        manager, pm, dm, players = _make_manager()
        dm.get_pending_powerup_for_target.return_value = {
            "id": 3,
            "powerup_type": "steal_preload",
        }
        with self.assertRaises(PowerUpError) as cm:
            manager.steal("attacker", "target", question_id=None)
        self.assertIn("already being targeted", str(cm.exception))


class TestHydration(unittest.TestCase):
    def test_hydrate_jinx_preload_sets_flags(self):
        manager, pm, dm, players = _make_manager()
        dm.apply_pending_powerups.return_value = [
            {
                "user_id": "attacker",
                "target_user_id": "target",
                "powerup_type": "jinx_preload",
            }
        ]
        manager.hydrate_pending_powerups(question_id=42)
        self.assertTrue(manager._get_daily_state("attacker").silenced)
        self.assertEqual(manager._get_daily_state("target").jinxed_by, "attacker")

    def test_hydrate_steal_preload_sets_flags(self):
        manager, pm, dm, players = _make_manager()
        dm.apply_pending_powerups.return_value = [
            {
                "user_id": "attacker",
                "target_user_id": "target",
                "powerup_type": "steal_preload",
            }
        ]
        manager.hydrate_pending_powerups(question_id=42)
        state = manager._get_daily_state("attacker")
        self.assertEqual(state.stealing_from, "target")
        # Streak cost deducted at hydration time: 5 - 3 = 2
        self.assertEqual(players["attacker"].answer_streak, 2)
        self.assertEqual(
            manager._get_daily_state("target").steal_attempt_by, "attacker"
        )

    def test_hydrate_empty_pending_is_noop(self):
        manager, pm, dm, players = _make_manager()
        dm.apply_pending_powerups.return_value = []
        manager.hydrate_pending_powerups(question_id=42)
        # No state changes
        self.assertFalse(manager._get_daily_state("attacker").silenced)


# ---------------------------------------------------------------------------
# Feature B: Retroactive targeting
# ---------------------------------------------------------------------------


class TestRetroactiveJinx(unittest.TestCase):
    def _setup_with_answered_target(self, streak_bonus=20):
        manager, pm, dm, players = _make_manager()
        # Mark target as already answered with a streak bonus
        target_state = manager._get_daily_state("target")
        target_state.is_correct = True
        target_state.bonuses = {"streak": streak_bonus}
        return manager, pm, dm, players

    def test_retro_jinx_transfers_half_streak(self):
        manager, pm, dm, players = self._setup_with_answered_target(streak_bonus=20)
        manager.jinx("attacker", "target", question_id=99)
        # attacker gains 10, target loses 10
        self.assertEqual(players["attacker"].score, 110)
        self.assertEqual(players["target"].score, 90)

    def test_retro_jinx_silences_attacker(self):
        manager, pm, dm, players = self._setup_with_answered_target(streak_bonus=20)
        manager.jinx("attacker", "target", question_id=99)
        self.assertTrue(manager._get_daily_state("attacker").silenced)

    def test_retro_jinx_marks_target_jinxed_by(self):
        manager, pm, dm, players = self._setup_with_answered_target(streak_bonus=20)
        manager.jinx("attacker", "target", question_id=99)
        self.assertEqual(manager._get_daily_state("target").jinxed_by, "attacker")

    def test_retro_jinx_logs_normal_jinx_type(self):
        manager, pm, dm, players = self._setup_with_answered_target(streak_bonus=20)
        manager.jinx("attacker", "target", question_id=99)
        dm.log_powerup_usage.assert_called_once_with("attacker", "jinx", "target", 99)

    def test_retro_jinx_no_streak_bonus_no_transfer(self):
        manager, pm, dm, players = self._setup_with_answered_target(streak_bonus=0)
        result = manager.jinx("attacker", "target", question_id=99)
        self.assertIn("no streak bonus", result)
        # No score changes
        self.assertEqual(players["attacker"].score, 100)
        self.assertEqual(players["target"].score, 100)

    def test_retro_jinx_rounds_down(self):
        """int(7 * 0.5) = 3, not 4."""
        manager, pm, dm, players = self._setup_with_answered_target(streak_bonus=7)
        manager.jinx("attacker", "target", question_id=99)
        self.assertEqual(players["attacker"].score, 103)
        self.assertEqual(players["target"].score, 97)

    def test_normal_jinx_not_triggered_when_target_unanswered(self):
        """Normal path: target hasn't answered, no immediate resolution."""
        manager, pm, dm, players = _make_manager()
        manager.jinx("attacker", "target", question_id=99)
        # No score changes yet
        self.assertEqual(players["attacker"].score, 100)
        self.assertEqual(players["target"].score, 100)
        self.assertEqual(manager._get_daily_state("target").jinxed_by, "attacker")

    def test_retro_jinx_triggered_after_on_guess(self):
        """Regression: on_guess must set is_correct so jinx sees it retroactively."""
        manager, pm, dm, players = _make_manager()
        dm.get_pending_multiplier.return_value = 1.0

        # Target answers correctly through the normal on_guess path
        manager.on_guess(
            player_id="target",
            player_name="Target",
            guess="answer",
            is_correct=True,
            points_earned=100,
            bonus_values={"streak": 20},
            question_id=99,
        )

        # Attacker jinxes after target has already answered
        result = manager.jinx("attacker", "target", question_id=99)

        # Should be retroactive: attacker gains 10, target loses 10
        self.assertEqual(players["attacker"].score, 110)
        self.assertEqual(players["target"].score, 90)
        self.assertIn("retroactive jinx", result)


class TestRetroactiveSteal(unittest.TestCase):
    def _setup_with_answered_target(self, target_bonuses=None):
        manager, pm, dm, players = _make_manager()
        target_state = manager._get_daily_state("target")
        target_state.is_correct = True
        target_state.score_earned = 50
        target_state.bonuses = (
            target_bonuses if target_bonuses is not None else {"try": 20}
        )
        return manager, pm, dm, players

    def test_retro_steal_deducts_higher_cost(self):
        manager, pm, dm, players = self._setup_with_answered_target()
        manager.steal("attacker", "target", question_id=99)
        # streak 5 − 5 (retro cost) = 0
        self.assertEqual(players["attacker"].answer_streak, 0)

    def test_retro_steal_transfers_bonuses_immediately(self):
        manager, pm, dm, players = self._setup_with_answered_target(
            target_bonuses={"try": 20}
        )
        manager.steal("attacker", "target", question_id=99)
        # try bonus of 20 transferred
        self.assertEqual(players["attacker"].score, 120)
        self.assertEqual(players["target"].score, 80)

    def test_retro_steal_nothing_to_steal(self):
        manager, pm, dm, players = self._setup_with_answered_target(target_bonuses={})
        result = manager.steal("attacker", "target", question_id=99)
        self.assertIn("nothing to steal", result)
        # No score changes
        self.assertEqual(players["attacker"].score, 100)
        self.assertEqual(players["target"].score, 100)

    def test_normal_steal_uses_lower_cost(self):
        """Normal path (target not answered): streak cost is STEAL_STREAK_COST."""
        manager, pm, dm, players = _make_manager()
        manager.steal("attacker", "target", question_id=99)
        # streak 5 − 3 = 2
        self.assertEqual(players["attacker"].answer_streak, 2)

    def test_normal_steal_no_immediate_transfer(self):
        manager, pm, dm, players = _make_manager()
        manager.steal("attacker", "target", question_id=99)
        # No score change yet
        self.assertEqual(players["attacker"].score, 100)
        self.assertEqual(players["target"].score, 100)


# ---------------------------------------------------------------------------
# DailyGameSimulator — overnight and retroactive
# ---------------------------------------------------------------------------


def _make_question():
    q = MagicMock()
    q.answer = "correct"
    q.clue_value = 100
    return q


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
    def test_retro_jinx_half_streak_transferred(self):
        """When jinx fires after target has answered, attacker gets half streak bonus."""
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
        sim.run(apply_end_of_day=False)

        target_state = sim.daily_state["T"]
        attacker_state = sim.daily_state["A"]

        streak_bonus = target_state.bonuses.get("streak", 0)
        # streak bonus should be stripped from target's bonuses
        self.assertEqual(streak_bonus, 0)
        # attacker has positive score_earned from streak transfer
        self.assertGreater(attacker_state.score_earned, 0)

    def test_normal_jinx_full_streak_transferred(self):
        """Check that a pre-answer jinx (normal path) strips full streak from target."""
        config = _make_config()
        attacker = Player(id="A", name="A", score=0, answer_streak=1)
        target = Player(id="T", name="T", score=0, answer_streak=5)
        initial_states = {"A": attacker, "T": target}

        # Jinx fires BEFORE target answers
        events = [
            PowerUpEvent(_ts(8, 30), "A", "jinx", "T"),
            GuessEvent(_ts(9), "T", "correct"),
        ]
        sim = DailyGameSimulator(
            _make_question(), ["correct"], None, events, initial_states, config
        )
        sim.run(apply_end_of_day=False)

        target_state = sim.daily_state["T"]
        attacker_state = sim.daily_state["A"]

        # Full streak bonus transferred (no fraction)
        streak_bonus = target_state.bonuses.get("streak", 0)
        self.assertEqual(streak_bonus, 0)
        self.assertGreater(attacker_state.score_earned, 0)


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


if __name__ == "__main__":
    unittest.main()
