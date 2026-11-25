import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
from data.readers.question import Question
from db.database import Database
from src.core.data_manager import DataManager
from src.core.events import GuessEvent, PowerUpEvent
from src.core.game_runner import GameRunner
from src.core.player_manager import PlayerManager
from src.core.powerup import PowerUpManager
from tests.src.core._powerup_helpers import make_config


class TestGameRunnerRestore(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.addCleanup(self.db.close)
        self.data_manager = DataManager(self.db)
        self.player_manager = PlayerManager(self.data_manager)

        # p1 enters the day with 100 points and a 3-day streak; logging the
        # question below snapshots that state.
        self.data_manager.create_player("p1", "P1")
        self.data_manager.update_lifetime_stats(
            "p1", score=100, answer_streak=3, season_score=100
        )
        self.data_manager.create_player("p2", "P2")

        self.question = Question(
            question="Q", answer="Alpha", category="C", clue_value=100
        )
        self.daily_question_id = self.data_manager.log_daily_question(self.question)
        _, _, self.question_db_id = self.data_manager.get_todays_daily_question()

        self.config = make_config(steal_cost=3)
        self.config.is_seasons_enabled.return_value = False
        # The selector only talks to datasets/Gemini and is unused by restore.
        with patch("src.core.game_runner.ConfigReader", return_value=self.config):
            self.game_runner = GameRunner(
                MagicMock(),
                self.data_manager,
                player_manager=self.player_manager,
            )
        self.game_runner.managers["powerup"] = PowerUpManager(
            self.player_manager, self.data_manager, config=self.config
        )
        self.game_runner.daily_q = self.question
        self.game_runner.daily_question_id = self.daily_question_id
        self.game_runner.question_db_id = self.question_db_id

    def _guess(self, player_id, text, guessed_at, is_correct=False):
        self.data_manager.log_player_guess(
            player_id, player_id, self.daily_question_id, text, is_correct
        )
        self.db.execute_update(
            "UPDATE guesses SET guessed_at = ? WHERE id = (SELECT MAX(id) FROM guesses)",
            (guessed_at,),
        )

    def _powerup(self, user_id, powerup_type, target_id, used_at):
        self.data_manager.log_powerup_usage(
            user_id, powerup_type, target_id, self.daily_question_id
        )
        self.db.execute_update(
            "UPDATE powerup_usage SET used_at = ? WHERE id = (SELECT MAX(id) FROM powerup_usage)",
            (used_at,),
        )

    def test_restore_game_state_replays_events_into_powerup_manager(self):
        """Restored state comes from replaying stored events with the snapshot and alt answers."""
        self.data_manager.add_alternative_answer(self.question_db_id, "Alt", "admin")
        self._powerup("p2", "rest", None, "2023-01-01 09:00:00")
        # Logged live as wrong; only counts as correct because of the alt answer.
        self._guess("p1", "Alt", "2023-01-01 10:00:00")
        # Today's players table drifted from the snapshot; restore must ignore it.
        self.data_manager.update_lifetime_stats("p1", score=9999, answer_streak=0)

        self.game_runner.restore_game_state()

        daily_state = self.game_runner.managers["powerup"].daily_state
        self.assertTrue(daily_state["p2"].is_resting)
        p1_state = daily_state["p1"]
        self.assertTrue(p1_state.is_correct)
        self.assertEqual(p1_state.guesses_count, 1)
        # 100 base + 20 first try + 10 before hint + 10 fastest + 20 streak (snapshot
        # streak 3 -> 4 days * 5); the drifted streak of 0 would give 145.
        self.assertEqual(p1_state.score_earned, 160)

    def test_restore_game_state_falls_back_to_all_players_when_no_snapshot(self):
        """When no snapshot exists, restore_game_state falls back to current players."""
        self.data_manager.update_lifetime_stats("p1", answer_streak=5)
        self._guess("p1", "Alpha", "2023-01-01 10:00:00", is_correct=True)

        # DataManager.get_daily_snapshot returns {} (never None) when nothing was
        # snapshotted, so the None branch is reached through failure injection.
        with patch.object(self.data_manager, "get_daily_snapshot", return_value=None):
            self.game_runner.restore_game_state()

        p1_state = self.game_runner.managers["powerup"].daily_state["p1"]
        # 140 + streak bonus capped at 25 (current streak 5 -> 6 days)
        self.assertEqual(p1_state.score_earned, 165)

    def test_restore_game_state_without_daily_question_is_noop(self):
        self.game_runner.daily_question_id = None
        self._guess("p1", "Alpha", "2023-01-01 10:00:00", is_correct=True)

        self.game_runner.restore_game_state()

        self.assertEqual(self.game_runner.managers["powerup"].daily_state, {})

    def test_restore_game_state_uses_snapshot_for_steal_preload(self):
        """
        Regression: after a bot restart, restore_game_state must use the pre-hydration
        snapshot (not current players) so that steal_preload events are replayed with the
        original streak.  When the post-deduction streak is 0, apply_steal silently bails
        out and stealing_from is never set — the steal is lost and powerup_used_today
        stays False, letting the thief use a second power-up.
        """
        steal_streak_cost = 3
        thief_id, target_id = "thief", "target"
        for player_id, name, streak in (
            (thief_id, "Thief", steal_streak_cost),  # exactly the cost in streak days
            (target_id, "Target", 5),
        ):
            self.data_manager.create_player(player_id, name)
            self.data_manager.update_lifetime_stats(
                player_id, score=1000, answer_streak=streak
            )
        # New day so the snapshot (pre-hydration) holds the original streaks.
        self.db.execute_update("UPDATE daily_questions SET sent_at = '2000-01-01'")
        question = Question(question="Q2", answer="Alpha", category="C", clue_value=100)
        self.daily_question_id = self.data_manager.log_daily_question(question)
        self.game_runner.daily_q = question
        self.game_runner.daily_question_id = self.daily_question_id

        # Overnight steal queued, then hydrated at the start of the day.
        self.data_manager.log_powerup_usage(thief_id, "steal_preload", target_id, None)
        pum = self.game_runner.managers["powerup"]
        pum.hydrate_pending_powerups(self.daily_question_id)
        self.assertEqual(self.player_manager.get_player(thief_id).answer_streak, 0)
        self._guess(target_id, "Alpha", "2023-01-01 10:05:00", is_correct=True)

        # Simulate the restart: transient state is gone, only the DB remains.
        pum.reset_daily_state()
        self.game_runner.restore_game_state()

        # With the snapshot (pre-deduction streak=3), apply_steal should correctly set
        # stealing_from — attack_powerup_used_today must be True so no second steal is possible.
        thief_state = pum.daily_state.get(thief_id)
        self.assertIsNotNone(thief_state, "Thief state should be in daily_state")
        self.assertEqual(
            thief_state.stealing_from,
            target_id,
            "stealing_from must be set after restore; with post-deduction streak=0 "
            "the old code silently dropped the steal and left attack_powerup_used_today=False",
        )
        self.assertTrue(
            thief_state.attack_powerup_used_today,
            "attack_powerup_used_today must be True after overnight steal is restored",
        )

    def test_fetch_daily_events_parsing(self):
        """Test that _fetch_daily_events correctly parses DB records into Event objects."""
        self._powerup("p2", "steal", "p1", "2023-01-01 09:00:00")
        self._guess("p1", "Alpha", "2023-01-01 10:00:00", is_correct=True)

        events = self.game_runner._fetch_daily_events(self.daily_question_id)

        self.assertEqual(len(events), 2)

        # Check Guess Event
        guess_event = next(e for e in events if isinstance(e, GuessEvent))
        self.assertEqual(guess_event.user_id, "p1")
        self.assertEqual(guess_event.guess_text, "Alpha")
        self.assertEqual(guess_event.timestamp, datetime(2023, 1, 1, 10, 0, 0))

        # Check PowerUp Event (Steal)
        powerup_event = next(e for e in events if isinstance(e, PowerUpEvent))
        self.assertEqual(powerup_event.user_id, "p2")
        self.assertEqual(powerup_event.powerup_type, "steal")
        self.assertEqual(powerup_event.target_user_id, "p1")
        self.assertEqual(powerup_event.timestamp, datetime(2023, 1, 1, 9, 0, 0))

    def test_fetch_daily_events_preserves_recorded_event_sequence(self):
        # Recorded order (power-up, then guess) wins over the conflicting timestamps.
        self._powerup("p2", "steal", "p1", "2023-01-01 10:00:00")
        self._guess("p1", "Alpha", "2023-01-01 09:00:00", is_correct=True)

        events = self.game_runner._fetch_daily_events(self.daily_question_id)

        self.assertEqual([event.event_sequence for event in events], [1, 2])
        self.assertIsInstance(events[0], PowerUpEvent)
        self.assertIsInstance(events[1], GuessEvent)


if __name__ == "__main__":
    unittest.main()
