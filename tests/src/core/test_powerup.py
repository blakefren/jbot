import unittest
from unittest.mock import MagicMock
from src.core.events import GuessContext
from src.core.powerup import PowerUpManager, PowerUpError
from src.core.player import Player


from datetime import date, timedelta


class TestPowerUpManager(unittest.TestCase):
    def setUp(self):
        self.player_manager = MagicMock()
        self.data_manager = MagicMock()
        self.players = {
            "1": Player(id="1", name="P1", score=100, answer_streak=3),
            "2": Player(id="2", name="P2", score=100, answer_streak=5),
            "3": Player(id="3", name="P3", score=100, answer_streak=0),
        }
        self.player_manager.get_player.side_effect = lambda pid: self.players.get(pid)

        # Mock get_last_correct_guess_date to return yesterday by default
        self.data_manager.get_last_correct_guess_date.return_value = (
            date.today() - timedelta(days=1)
        )
        self.data_manager.get_today.return_value = date.today()

        # Mock update_score to actually update the player object for testing assertions
        def update_score(pid, amount):
            if pid in self.players:
                self.players[pid].score += amount

        self.player_manager.update_score.side_effect = update_score

        # Mock reset_streak
        def reset_streak(pid):
            if pid in self.players:
                self.players[pid].answer_streak = 0

        self.player_manager.reset_streak.side_effect = reset_streak

        # Mock set_streak
        def set_streak(pid, value):
            if pid in self.players:
                self.players[pid].answer_streak = value

        self.player_manager.set_streak.side_effect = set_streak

        # Mock get_pending_multiplier to return 0.0 by default (no rest bonus)
        self.data_manager.get_pending_multiplier.return_value = 0.0
        # No pending overnight powerups by default
        self.data_manager.get_pending_powerup.return_value = None
        self.data_manager.get_pending_powerup_for_target.return_value = None

    def test_rest_basic(self):
        """Test that rest marks the player as resting and sets pending multiplier."""
        self.data_manager.get_pending_multiplier = MagicMock(return_value=0.0)
        self.data_manager.set_pending_multiplier = MagicMock()
        manager = PowerUpManager(self.player_manager, self.data_manager)
        public_msg, private_msg = manager.rest("1", "q1", "Correct Answer")
        self.assertIn("resting", public_msg)
        self.assertIn("Correct Answer", private_msg)
        self.assertTrue(manager._get_daily_state("1").is_resting)
        self.data_manager.set_pending_multiplier.assert_called_once_with("1", 1.2)

    def test_rest_already_answered(self):
        """Test that resting after a correct answer is blocked."""
        self.data_manager.get_last_correct_guess_date.return_value = (
            self.data_manager.get_today.return_value
        )
        self.data_manager.get_today.return_value = date.today()
        self.data_manager.get_last_correct_guess_date.return_value = date.today()
        manager = PowerUpManager(self.player_manager, self.data_manager)
        with self.assertRaises(PowerUpError) as cm:
            manager.rest("1", "q1", "Correct Answer")
        self.assertIn("already answered correctly", str(cm.exception))

    def test_rest_blocks_guesses(self):
        """Test that a resting player cannot submit guesses."""
        manager = PowerUpManager(self.player_manager, self.data_manager)
        manager._get_daily_state("1").is_resting = True
        can_answer, reason = manager.can_answer("1")
        self.assertFalse(can_answer)
        self.assertIn("resting", reason)

    def test_rest_resolves_steal_whiff(self):
        """Test that an existing steal attempt is cleared when the target rests."""
        manager = PowerUpManager(self.player_manager, self.data_manager)
        # Simulate P1 having stolen from P2
        manager._get_daily_state("2").steal_attempt_by = "1"
        public_msg, _ = manager.rest("2", "q1", "Ans")
        self.assertIn("whiffed", public_msg)
        # steal_attempt_by should be cleared
        self.assertIsNone(manager._get_daily_state("2").steal_attempt_by)

    def test_rest_resolves_jinx_whiff(self):
        """Test that a jinx is cleared when the target rests."""
        manager = PowerUpManager(self.player_manager, self.data_manager)
        manager._get_daily_state("2").jinxed_by = "1"
        public_msg, _ = manager.rest("2", "q1", "Ans")
        self.assertIn("no effect", public_msg)
        self.assertIsNone(manager._get_daily_state("2").jinxed_by)

    def test_rest_powerup_lockout(self):
        """Test that resting blocks other power-ups."""
        manager = PowerUpManager(self.player_manager, self.data_manager)
        manager.rest("1", "q1", "Ans")
        with self.assertRaises(PowerUpError) as cm:
            manager.jinx("1", "2", "q1")
        self.assertIn("already used a power-up today", str(cm.exception))

    def test_rest_next_day_multiplier(self):
        """Test that the 1.2x rest multiplier is applied on the next correct answer."""
        self.data_manager.get_pending_multiplier = MagicMock(return_value=1.2)
        self.data_manager.clear_pending_multiplier = MagicMock()
        manager = PowerUpManager(self.player_manager, self.data_manager)
        ctx = GuessContext(1, "P1", "ans", True, points_earned=100)
        msgs = manager.on_guess(ctx)
        # 1.2x means +20 on 100 pts
        self.assertTrue(any("Rest bonus" in m for m in msgs))
        self.assertEqual(self.players["1"].score, 120)  # 100 base + 20 bonus
        self.data_manager.clear_pending_multiplier.assert_called_once_with("1")

    def test_jinx_basic(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        msg = manager.jinx("1", "2", "q1")
        self.assertIn("jinx is set", msg)
        # No cost for jinx
        self.assertEqual(self.players["1"].score, 100)
        self.assertEqual(manager._get_daily_state("2").jinxed_by, "1")
        self.assertTrue(manager._get_daily_state("1").silenced)

    def test_steal_success(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)

        # Attacker steals
        msg = manager.steal("1", "2", "q1")
        self.assertIn(f"sacrificed {manager.engine.steal_streak_cost} streak days", msg)
        self.assertEqual(
            self.players["1"].answer_streak,
            max(0, 3 - manager.engine.steal_streak_cost),
        )  # 3 - cost

        # Target answers correctly and earns bonuses
        # We simulate on_guess for the TARGET ("2")
        # Pre-condition: Target earns bonuses
        # Note: on_guess calls resolve_steal(target_id)

        # We need to manually set bonuses_today because on_guess sets it
        # But on_guess calls resolve_steal AFTER setting it.

        ctx = GuessContext(
            2, "P2", "ans", True, points_earned=100, bonus_values={"fastest": 10}
        )
        msgs = manager.on_guess(ctx)

        self.assertTrue(any("stole 10 pts" in m for m in msgs))
        self.assertEqual(self.players["1"].score, 110)  # 100 + 10 stolen
        self.assertEqual(self.players["2"].score, 90)  # 100 - 10 stolen

    def test_steal_no_points(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        msg = manager.steal("1", "2", "q1")
        self.assertIn(f"sacrificed {manager.engine.steal_streak_cost} streak days", msg)

        # Attacker answers correctly but target has no bonuses
        msgs = manager.on_guess(GuessContext(1, "P1", "ans", True))
        # Should be no steal message
        self.assertFalse(any("stole" in m for m in msgs))

    def test_steal_invalid_player(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        with self.assertRaises(PowerUpError) as cm:
            manager.steal("1", "999", "q1")
        self.assertIn("Invalid player", str(cm.exception))

    def test_on_guess_correct(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        msgs = manager.on_guess(
            GuessContext("1", "P1", "guess", True, points_earned=100)
        )
        self.assertIsInstance(msgs, list)

    def test_on_guess_incorrect(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        msgs = manager.on_guess(GuessContext("1", "P1", "guess", False))
        self.assertIsInstance(msgs, list)
        self.assertEqual(len(msgs), 0)

    def test_jinx_invalid_attacker(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        with self.assertRaises(PowerUpError) as cm:
            manager.jinx("999", "1", "q1")
        self.assertIn("Invalid player", str(cm.exception))

    def test_can_answer_hint_sent(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)

        manager._get_daily_state("1").silenced = True

        # Case 1: Hint NOT sent -> Should be False
        can_answer, reason = manager.can_answer("1", hint_sent=False)
        self.assertFalse(can_answer)
        self.assertIn("Jinxed", reason)

        # Case 2: Hint SENT -> Should be True
        can_answer, reason = manager.can_answer("1", hint_sent=True)
        self.assertTrue(can_answer)

    def test_jinx_invalid_target(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        with self.assertRaises(PowerUpError) as cm:
            manager.jinx("1", "999", "q1")
        self.assertIn("Invalid player", str(cm.exception))

    def test_steal_first_try_bonus(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)

        # Attacker (P1) steals from Target (P2)
        manager.steal("1", "2", "q1")

        # Target (P2) answers correctly on first try (bonus)
        # on_guess calls resolve_steal
        msgs = manager.on_guess(
            GuessContext(
                2, "P2", "ans", True, points_earned=120, bonus_values={"first_try": 20}
            )
        )

        # Verify steal — only canonical try_1 is present (not first_try alias), so full 20 is stealable
        self.assertTrue(any("stole 20 pts" in m for m in msgs))
        self.assertEqual(self.players["1"].score, 120)  # 100 + 20
        self.assertEqual(self.players["2"].score, 80)  # 100 - 20

    def test_jinx_limit(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        # First use
        msg = manager.jinx("1", "2", "q1")
        self.assertIn("jinx is set", msg)

        # Second use
        with self.assertRaises(PowerUpError) as cm:
            manager.jinx("1", "3", "q1")
        self.assertIn("already used a power-up today", str(cm.exception))

    def test_steal_limit(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        # First use
        msg = manager.steal("1", "2", "q1")
        self.assertIn(f"sacrificed {manager.engine.steal_streak_cost} streak days", msg)

        # Second use
        with self.assertRaises(PowerUpError) as cm:
            manager.steal("1", "3", "q1")
        self.assertIn("already used a power-up today", str(cm.exception))

    def test_powerup_lockout(self):
        """Test that using one powerup blocks others."""
        manager = PowerUpManager(self.player_manager, self.data_manager)

        # Use Jinx
        manager.jinx("1", "2", "q1")

        # Try Steal
        with self.assertRaises(PowerUpError) as cm:
            manager.steal("1", "3", "q1")
        self.assertIn("already used a power-up today", str(cm.exception))

    def test_reset_daily_state(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        manager.jinx("1", "2", "q1")
        self.assertTrue(manager._get_daily_state("1").silenced)
        self.assertTrue(manager._get_daily_state("1").powerup_used_today)

        manager.reset_daily_state()
        state = manager._get_daily_state("1")
        self.assertFalse(state.silenced)
        self.assertFalse(state.powerup_used_today)
        self.assertIsNone(state.jinxed_by)

    def test_powerups_blocked_without_question(self):
        """
        When question_id is None, jinx/steal enter overnight pre-load mode
        (not an error). Rest still requires an active question.
        """
        manager = PowerUpManager(self.player_manager, self.data_manager)

        # Jinx with question_id=None → overnight pre-load, should succeed
        result = manager.jinx("1", "2", None)
        self.assertIn("queued for tomorrow", result)

        # Reset state then try steal overnight — should also succeed.
        # (attacker "1" now has a pending overnight powerup; use a fresh manager)
        manager2 = PowerUpManager(self.player_manager, self.data_manager)
        result2 = manager2.steal("1", "2", None)
        self.assertIn("queued", result2)

        # Rest still requires an active question
        with self.assertRaises(PowerUpError) as cm3:
            manager.rest("1", None, "Ans")
        self.assertEqual(str(cm3.exception), "There is no active question right now.")

    def test_duplicate_jinx(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        # First jinx should succeed
        msg1 = manager.jinx("1", "2", "q1")
        self.assertIn("jinx is set", msg1)

        # Verify first usage was logged
        self.assertEqual(self.data_manager.log_powerup_usage.call_count, 1)
        first_call = self.data_manager.log_powerup_usage.call_args_list[0]
        self.assertEqual(first_call[0], ("1", "jinx", "2", "q1"))

        # Second jinx on same target should fail
        # Need a different attacker because attacker 1 is now silenced/used powerup
        with self.assertRaises(PowerUpError) as cm:
            manager.jinx("3", "2", "q1")
        self.assertIn("already been jinxed", str(cm.exception))

        # Verify second usage was NOT logged (still only 1 call)
        self.assertEqual(self.data_manager.log_powerup_usage.call_count, 1)

    def test_duplicate_steal(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        # First steal should succeed
        msg1 = manager.steal("1", "2", "q1")
        self.assertIn(
            f"sacrificed {manager.engine.steal_streak_cost} streak days", msg1
        )

        # Verify first usage was logged
        self.assertEqual(self.data_manager.log_powerup_usage.call_count, 1)
        first_call = self.data_manager.log_powerup_usage.call_args_list[0]
        self.assertEqual(first_call[0], ("1", "steal", "2", "q1"))

        # Second steal on same target should fail
        with self.assertRaises(PowerUpError) as cm:
            manager.steal("3", "2", "q1")
        self.assertIn("already being targeted for theft", str(cm.exception))

        # Verify second usage was NOT logged (still only 1 call)
        self.assertEqual(self.data_manager.log_powerup_usage.call_count, 1)

    def test_jinx_resolution_message_content(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        manager.jinx("1", "2", "q1")

        # Target (P2) answers correctly with a streak bonus
        # on_guess calls resolve_jinx
        msgs = manager.on_guess(
            GuessContext(
                2, "P2", "ans", True, points_earned=100, bonus_values={"streak": 50}
            )
        )

        # Verify message reflects the transfer
        self.assertTrue(any("swiped" in m and "streak bonus" in m for m in msgs))
        # Verify attacker (P1) gained the streak bonus
        self.assertEqual(self.players["1"].score, 150)  # 100 base + 50 stolen streak
        # Verify target (P2) lost the streak bonus
        self.assertEqual(self.players["2"].score, 50)  # 100 base - 50 stolen streak

    def test_jinx_steals_streak_bonus(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        manager.jinx("1", "2", "q1")

        # Simulate P2 answering correctly.
        # Assume P2 had streak 5, and GuessHandler incremented it to 6 before calling on_guess.
        self.players["2"].answer_streak = 6

        # Mock bonus messages
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

        # on_guess calls resolve_jinx
        msgs = manager.on_guess(ctx)

        # Streak should NOT be frozen — set_streak should not be called
        self.player_manager.set_streak.assert_not_called()

        # Verify message reflects the transfer
        self.assertTrue(any("swiped" in m and "streak bonus" in m for m in msgs))

        # Verify streak message removed
        self.assertEqual(len(bonus_messages), 0)

        # Verify points_earned updated in ctx (target net)
        self.assertEqual(ctx.points_earned, 100)

        # Verify attacker (P1) gained the stolen streak bonus
        self.assertEqual(self.players["1"].score, 125)  # 100 base + 25 stolen streak
        # Verify target (P2) had the streak bonus deducted
        self.assertEqual(self.players["2"].score, 75)  # 100 base - 25 stolen streak

    def test_jinx_no_streak_bonus_no_effect(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        manager.jinx("1", "3", "q1")  # P3 has 0 streak

        # Simulate P3 answering correctly.
        # GuessHandler increments 0 -> 1.
        self.players["3"].answer_streak = 1

        msgs = manager.on_guess(GuessContext(3, "P3", "ans", True, points_earned=100))

        # Streak should NOT be frozen — set_streak should not be called
        self.player_manager.set_streak.assert_not_called()

        # Verify message reflects that there was nothing to steal
        self.assertTrue(any("no streak bonus to steal" in m for m in msgs))

    def test_steal_resolution_message_content(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        manager.steal("1", "2", "q1")

        # Target (P2) answers correctly with bonuses
        msgs = manager.on_guess(
            GuessContext(
                2,
                "P2",
                "ans",
                True,
                points_earned=100,
                bonus_values={"fastest": 20, "first_try": 10},
            )
        )

        # Verify message contains points stolen
        self.assertTrue(any("stole 30 pts" in m for m in msgs))

    def test_steal_includes_rest_bonus(self):
        """Rest bonus earned on answer day must be included in stealable amount."""
        # P2 rested yesterday, so has a pending 1.2x multiplier
        self.data_manager.get_pending_multiplier.side_effect = lambda pid: (
            1.2 if pid == "2" else 0.0
        )

        manager = PowerUpManager(self.player_manager, self.data_manager)
        # P1 steals from P2
        manager.steal("1", "2", "q1")

        # P2 answers correctly: base 100 pts + before_hint bonus 10 pts = 110 pts
        # Rest multiplier on 110: round(110 * 0.2) = 22 pts rest bonus
        # Stealable = before_hint (10) + rest (22) = 32 pts
        msgs = manager.on_guess(
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
        self.assertEqual(self.players["1"].score, 132)  # 100 + 32 stolen
        # P2 starts at 100; +22 rest bonus applied, -32 stolen (base 110 not added here,
        # that's GuessHandler's responsibility, not PowerUpManager's)
        self.assertEqual(self.players["2"].score, 90)  # 100 + 22 rest - 32 stolen


class TestStealEnforcementAndScaling(unittest.TestCase):
    """Tests for steal enforcement (streak=0 rejected) and partial-steal scaling."""

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

    # ------------------------------------------------------------------
    # Enforcement: streak=0 rejects steal in all paths
    # ------------------------------------------------------------------

    def test_zero_streak_daytime_forward_rejected(self):
        """Player with 0 streak cannot initiate a forward daytime steal."""
        m = self._make_manager()
        with self.assertRaises(PowerUpError) as cm:
            m.steal("zero", "target", "q1")
        self.assertIn("streak days", str(cm.exception))
        self.assertIsNone(m._get_daily_state("target").steal_attempt_by)

    def test_zero_streak_daytime_retro_rejected(self):
        """Player with 0 streak cannot steal retroactively after target answers."""
        m = self._make_manager()
        m._get_daily_state("target").is_correct = True
        m._get_daily_state("target").bonuses = {"before_hint": 10}
        with self.assertRaises(PowerUpError) as cm:
            m.steal("zero", "target", "q1")
        self.assertIn("streak days", str(cm.exception))
        self.assertIn("before_hint", m._get_daily_state("target").bonuses)

    def test_zero_streak_overnight_rejected(self):
        """Player with 0 streak cannot queue an overnight steal."""
        m = self._make_manager()
        with self.assertRaises(PowerUpError) as cm:
            m.steal("zero", "target", None)
        self.assertIn("streak days", str(cm.exception))
        self.data_manager.log_powerup_usage.assert_not_called()

    def test_zero_streak_target_still_stealable(self):
        """After a failed zero-streak steal, the target can be stolen by someone else."""
        m = self._make_manager()
        with self.assertRaises(PowerUpError):
            m.steal("zero", "target", "q1")
        # Give the partial player enough streak for a full steal, then steal succeeds
        self.players["partial"].answer_streak = 3
        msg = m.steal("partial", "target", "q1")
        self.assertIn("streak days", msg)

    # ------------------------------------------------------------------
    # Partial steal (forward): fraction of bonuses stolen when target answers
    # ------------------------------------------------------------------

    def test_partial_steal_forward_steals_fraction(self):
        """Forward steal with 2 streak days (cost 3) gets round(30 * 2/3) = 20 pts."""
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

    def test_partial_steal_forward_target_bonuses_cleared(self):
        """After partial forward steal resolves, target bonuses dict is emptied."""
        m = self._make_manager()
        m.steal("partial", "target", "q1")

        ctx = GuessContext(
            "target",
            "Target",
            "ans",
            True,
            points_earned=120,
            bonus_values={"before_hint": 10, "fastest_1": 10},
        )
        m.on_guess(ctx)

        self.assertEqual(m._get_daily_state("target").bonuses, {})
        self.assertIsNone(m._get_daily_state("target").steal_attempt_by)

    # ------------------------------------------------------------------
    # Partial steal (retroactive): fraction of bonuses stolen immediately
    # ------------------------------------------------------------------

    def test_partial_steal_retro_steals_fraction(self):
        """Retro steal with 2 streak (cost 5) gets round(30 * 2/5) = 12 pts immediately."""
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

    def test_partial_steal_retro_target_bonuses_cleared(self):
        """After retroactive partial steal, target bonuses dict is cleared."""
        m = self._make_manager()
        tgt = m._get_daily_state("target")
        tgt.is_correct = True
        tgt.score_earned = 110
        tgt.bonuses = {"before_hint": 10}

        m.steal("partial", "target", "q1")

        self.assertEqual(m._get_daily_state("target").bonuses, {})
