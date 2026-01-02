import unittest
from unittest.mock import MagicMock
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

        # Mock update_score to actually update the player object for testing assertions
        def update_score(pid, amount):
            if pid in self.players:
                self.players[pid].score += amount

        self.player_manager.update_score.side_effect = update_score

        # Mock activate/deactivate shield
        def activate_shield(pid):
            if pid in self.players:
                self.players[pid].active_shield = True

        self.player_manager.activate_shield.side_effect = activate_shield

        def deactivate_shield(pid):
            if pid in self.players:
                self.players[pid].active_shield = False

        self.player_manager.deactivate_shield.side_effect = deactivate_shield

        # Mock reset_streak
        def reset_streak(pid):
            if pid in self.players:
                self.players[pid].answer_streak = 0

        self.player_manager.reset_streak.side_effect = reset_streak

    def test_jinx_basic(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        msg = manager.jinx("1", "2", "q1")
        self.assertIn("jinxed", msg)
        # No cost for jinx
        self.assertEqual(self.players["1"].score, 100)
        self.assertEqual(manager._get_daily_state("2").jinxed_by, "1")
        self.assertTrue(manager._get_daily_state("1").silenced)

    def test_jinx_with_shield(self):
        # Shield is now tracked in daily_state, not player object directly for this manager logic
        # But use_shield sets it in daily_state
        manager = PowerUpManager(self.player_manager, self.data_manager)
        manager.use_shield("2", "q1")

        msg = manager.jinx("1", "2", "q1")
        self.assertIn("Shield blocked", msg)
        self.assertTrue(manager._get_daily_state("2").shield_used)
        # jinx_status is no longer used, we check if jinxed_by is NOT set
        self.assertIsNone(manager._get_daily_state("2").jinxed_by)

    def test_use_shield_basic(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        msg = manager.use_shield("1", "q1")
        self.assertIn("Shield active", msg)
        self.assertTrue(manager._get_daily_state("1").shield_active)
        # No upfront cost
        self.assertEqual(self.players["1"].score, 100)

    def test_use_shield_already_active(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        manager.use_shield("1", "q1")
        with self.assertRaises(PowerUpError) as cm:
            manager.use_shield("1", "q1")
        self.assertIn("already used a power-up today", str(cm.exception))

    def test_steal_success(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)

        # Attacker steals
        msg = manager.steal("1", "2", "q1")
        self.assertIn("sacrificed their streak", msg)
        self.assertEqual(self.players["1"].answer_streak, 0)

        # Target answers correctly and earns bonuses
        # We simulate on_guess for the TARGET ("2")
        # Pre-condition: Target earns bonuses
        # Note: on_guess calls resolve_steal(target_id)

        # We need to manually set bonuses_today because on_guess sets it
        # But on_guess calls resolve_steal AFTER setting it.

        msgs = manager.on_guess(
            2, "P2", "ans", True, points_earned=100, bonus_values={"first_place": 10}
        )

        self.assertTrue(any("stole 10 points" in m for m in msgs))
        self.assertEqual(self.players["1"].score, 110)  # 100 + 10 stolen
        self.assertEqual(self.players["2"].score, 90)  # 100 - 10 stolen

    def test_steal_no_points(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        msg = manager.steal("1", "2", "q1")
        self.assertIn("sacrificed their streak", msg)

        # Attacker answers correctly but target has no bonuses
        msgs = manager.on_guess(1, "P1", "ans", True)
        # Should be no steal message
        self.assertFalse(any("stole" in m for m in msgs))

    def test_wager_points_basic(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        msg = manager.place_wager("1", 10, "q1")
        self.assertIn("wagered 10 points", msg)
        self.assertEqual(self.players["1"].score, 90)
        self.assertEqual(manager._get_daily_state("1").wager, 10)

    def test_wager_points_max_wager(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        msg = manager.place_wager("1", 100, "q1")
        self.assertIn("wagered 25 points", msg)  # 100//4 = 25
        self.assertEqual(self.players["1"].score, 75)
        self.assertEqual(manager._get_daily_state("1").wager, 25)

    def test_wager_points_invalid(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        with self.assertRaises(PowerUpError) as cm:
            manager.place_wager("1", 0, "q1")
        self.assertIn("Invalid wager amount", str(cm.exception))
        with self.assertRaises(PowerUpError) as cm2:
            manager.place_wager("1", 200, "q1")
        self.assertIn("Invalid wager amount", str(cm2.exception))

    def test_resolve_wager_win(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        manager.place_wager("1", 20, "q1")
        msg = manager.resolve_wager("1", True)
        self.assertIn("won the wager", msg)
        self.assertEqual(manager._get_daily_state("1").wager, 0)

    def test_resolve_wager_lose(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        manager.place_wager("1", 20, "q1")
        msg = manager.resolve_wager("1", False)
        self.assertIn("lost the wager", msg)
        self.assertEqual(manager._get_daily_state("1").wager, 0)

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

    def test_teamup_success(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        msg = manager.teamup("1", "2", "q1")
        self.assertEqual(self.players["1"].score, 75)
        self.assertEqual(manager._get_daily_state("1").team_partner, "2")

    def test_teamup_already_teamed(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        manager.teamup("1", "2", "q1")
        with self.assertRaises(PowerUpError) as cm:
            manager.teamup("1", "3", "q1")
        self.assertIn("already teamed up", str(cm.exception))

    def test_teamup_not_enough_points(self):
        self.players["1"].score = 10
        manager = PowerUpManager(self.player_manager, self.data_manager)
        with self.assertRaises(PowerUpError) as cm:
            manager.teamup("1", "2", "q1")
        self.assertIn("need at least", str(cm.exception))

    def test_teamup_invalid_player(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        with self.assertRaises(PowerUpError) as cm:
            manager.teamup("1", "999", "q1")
        self.assertIn("Invalid player", str(cm.exception))

    def test_resolve_teamup(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        manager.teamup("1", "2", "q1")
        manager.resolve_teamup("1", True)
        self.assertTrue(manager._get_daily_state("1").team_success)
        self.assertTrue(manager._get_daily_state("2").team_success)

    def test_steal_invalid_player(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        with self.assertRaises(PowerUpError) as cm:
            manager.steal("1", "999", "q1")
        self.assertIn("Invalid player", str(cm.exception))

    def test_on_guess_correct(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        manager.place_wager("1", 20, "q1")
        manager.on_guess("1", "P1", "guess", True)
        self.assertEqual(manager._get_daily_state("1").wager, 0)

    def test_on_guess_incorrect(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        manager.place_wager("1", 20, "q1")
        manager.on_guess("1", "P1", "guess", False)
        self.assertEqual(manager._get_daily_state("1").wager, 0)

    def test_jinx_invalid_attacker(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        with self.assertRaises(PowerUpError) as cm:
            manager.jinx("999", "1", "q1")
        self.assertIn("Invalid player", str(cm.exception))

    def test_can_answer_hint_sent(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        # Set silenced to True
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

    def test_place_wager_invalid_player(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        with self.assertRaises(PowerUpError) as cm:
            manager.place_wager("999", 10, "q1")
        self.assertIn("Invalid player", str(cm.exception))

    def test_shield_shatter_penalty(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        # Player 1 activates shield
        manager.use_shield("1", "q1")
        self.assertTrue(manager._get_daily_state("1").shield_active)
        self.assertFalse(manager._get_daily_state("1").shield_used)

        # End of day check - Shield unused
        messages = manager.check_shield_usage()

        # Verify penalty
        self.assertEqual(self.players["1"].score, 90)  # 100 - 10
        self.assertTrue(any("shattered" in m for m in messages))

    def test_steal_first_try_bonus(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)

        # Attacker (P1) steals from Target (P2)
        manager.steal("1", "2", "q1")

        # Target (P2) answers correctly on first try (bonus)
        # on_guess calls resolve_steal
        msgs = manager.on_guess(
            2, "P2", "ans", True, points_earned=120, bonus_values={"first_try": 20}
        )

        # Verify steal
        self.assertTrue(any("stole 20 points" in m for m in msgs))
        self.assertEqual(self.players["1"].score, 120)  # 100 + 20
        self.assertEqual(self.players["2"].score, 80)  # 100 - 20

    def test_jinx_limit(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        # First use
        msg = manager.jinx("1", "2", "q1")
        self.assertIn("jinxed", msg)

        # Second use
        with self.assertRaises(PowerUpError) as cm:
            manager.jinx("1", "3", "q1")
        self.assertIn("already used a power-up today", str(cm.exception))

    def test_steal_limit(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        # First use
        msg = manager.steal("1", "2", "q1")
        self.assertIn("sacrificed their streak", msg)

        # Second use
        with self.assertRaises(PowerUpError) as cm:
            manager.steal("1", "3", "q1")
        self.assertIn("already used a power-up today", str(cm.exception))

    def test_powerup_lockout(self):
        """Test that using one powerup blocks others."""
        manager = PowerUpManager(self.player_manager, self.data_manager)

        # Use Shield
        manager.use_shield("1", "q1")

        # Try Jinx
        with self.assertRaises(PowerUpError) as cm:
            manager.jinx("1", "2", "q1")
        self.assertIn("already used a power-up today", str(cm.exception))

        # Try Steal
        with self.assertRaises(PowerUpError) as cm2:
            manager.steal("1", "3", "q1")
        self.assertIn("already used a power-up today", str(cm2.exception))

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
        manager = PowerUpManager(self.player_manager, self.data_manager)

        # Test Jinx
        with self.assertRaises(PowerUpError) as cm:
            manager.jinx("1", "2", None)
        self.assertEqual(str(cm.exception), "There is no active question right now.")

        # Test Steal
        with self.assertRaises(PowerUpError) as cm2:
            manager.steal("1", "2", None)
        self.assertEqual(str(cm2.exception), "There is no active question right now.")

        # Test Shield
        with self.assertRaises(PowerUpError) as cm3:
            manager.use_shield("1", None)
        self.assertEqual(str(cm3.exception), "There is no active question right now.")

        # Test Wager
        with self.assertRaises(PowerUpError) as cm4:
            manager.place_wager("1", 10, None)
        self.assertEqual(str(cm4.exception), "There is no active question right now.")

    def test_duplicate_jinx(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        # First jinx should succeed
        msg1 = manager.jinx("1", "2", "q1")
        self.assertIn("jinxed", msg1)

        # Second jinx on same target should fail
        # Need a different attacker because attacker 1 is now silenced/used powerup
        with self.assertRaises(PowerUpError) as cm:
            manager.jinx("3", "2", "q1")
        self.assertIn("already been jinxed", str(cm.exception))

    def test_duplicate_steal(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        # First steal should succeed
        msg1 = manager.steal("1", "2", "q1")
        self.assertIn("sacrificed their streak", msg1)

        # Second steal on same target should fail
        with self.assertRaises(PowerUpError) as cm:
            manager.steal("3", "2", "q1")
        self.assertIn("already being targeted for theft", str(cm.exception))

    def test_jinx_resolution_message_content(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        manager.jinx("1", "2", "q1")

        # Target (P2) answers correctly with a streak bonus
        # on_guess calls resolve_jinx
        msgs = manager.on_guess(
            2, "P2", "ans", True, points_earned=100, bonus_values={"streak": 50}
        )

        # Verify message contains points lost
        self.assertTrue(any("streak bonus of 50 points" in m for m in msgs))

    def test_jinx_freezes_streak(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        manager.jinx("1", "2", "q1")

        # Simulate P2 answering correctly.
        # Assume P2 had streak 5, and GuessHandler incremented it to 6 before calling on_guess.
        self.players["2"].answer_streak = 6

        # Mock bonus messages
        bonus_messages = ["🔥 6 day streak! (+25)"]
        points_tracker = {"earned": 125}  # 100 base + 25 streak

        # on_guess calls resolve_jinx
        msgs = manager.on_guess(
            2,
            "P2",
            "ans",
            True,
            points_earned=125,
            bonus_values={"streak": 25},
            bonus_messages=bonus_messages,
            points_tracker=points_tracker,
        )

        # Verify streak was decremented back to 5
        self.player_manager.set_streak.assert_called_with("2", 5)

        # Verify points deducted
        self.assertTrue(any("froze their streak bonus" in m for m in msgs))

        # Verify streak message removed
        self.assertEqual(len(bonus_messages), 0)

        # Verify points tracker updated
        self.assertEqual(points_tracker["earned"], 100)

    def test_jinx_freezes_streak_no_bonus(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        manager.jinx("1", "3", "q1")  # P3 has 0 streak

        # Simulate P3 answering correctly.
        # GuessHandler increments 0 -> 1.
        self.players["3"].answer_streak = 1

        msgs = manager.on_guess(
            3, "P3", "ans", True, points_earned=100, bonus_values={}
        )

        # Verify streak was decremented back to 0
        self.player_manager.set_streak.assert_called_with("3", 0)

        # Verify message
        self.assertTrue(any("froze their streak" in m for m in msgs))

    def test_steal_resolution_message_content(self):
        manager = PowerUpManager(self.player_manager, self.data_manager)
        manager.steal("1", "2", "q1")

        # Target (P2) answers correctly with bonuses
        msgs = manager.on_guess(
            2,
            "P2",
            "ans",
            True,
            points_earned=100,
            bonus_values={"first_place": 20, "first_try": 10},
        )

        # Verify message contains points stolen
        self.assertTrue(any("stole 30 points" in m for m in msgs))
