import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
from src.core.game_runner import GameRunner
from src.core.events import GuessEvent, PowerUpEvent
from src.core.player import Player
from src.core.state import DailyPlayerState
from data.readers.question import Question


class TestGameRunnerRestore(unittest.TestCase):
    def setUp(self):
        self.mock_question_selector = MagicMock()
        self.mock_data_manager = MagicMock()
        self.game_runner = GameRunner(
            self.mock_question_selector, self.mock_data_manager
        )

        # Setup basic daily question
        self.mock_question = Question(
            question="Q", answer="A", category="C", clue_value=100
        )
        self.mock_question.id = "q1"
        self.game_runner.daily_q = self.mock_question
        self.game_runner.daily_question_id = 123
        self.game_runner.question_db_id = 999

        # Mock DataManager returns
        # restore_game_state now prefers get_daily_snapshot over get_all_players
        self.snapshot_players = {
            "p1": Player(id="p1", name="P1", score=100, answer_streak=3)
        }
        self.mock_data_manager.get_daily_snapshot.return_value = self.snapshot_players
        self.mock_data_manager.get_all_players.return_value = {}
        self.mock_data_manager.get_alternative_answers.return_value = []
        self.mock_data_manager.get_hint_sent_timestamp.return_value = None

    @patch("src.core.game_runner.DailyGameSimulator")
    def test_restore_game_state_calls_simulator(self, MockSimulator):
        """Test that restore_game_state initializes and runs the simulator correctly."""
        # Setup mock events
        self.mock_data_manager.get_guesses_for_daily_question.return_value = [
            {"guessed_at": "2023-01-01 10:00:00", "player_id": "p1", "guess_text": "A"}
        ]
        self.mock_data_manager.get_powerup_usages_for_question.return_value = [
            {
                "used_at": "2023-01-01 09:00:00",
                "user_id": "p1",
                "powerup_type": "shield",
                "target_user_id": None,
            }
        ]

        # Setup Simulator Mock
        mock_sim_instance = MockSimulator.return_value
        mock_sim_instance.daily_state = {"p1": {"shield_active": True}}

        # Execute
        self.game_runner.restore_game_state()

        # Verify snapshot is preferred over get_all_players
        self.mock_data_manager.get_daily_snapshot.assert_called_with(123)
        self.mock_data_manager.get_all_players.assert_not_called()

        # Verify Simulator Initialization
        MockSimulator.assert_called_once()
        args, _ = MockSimulator.call_args
        self.assertEqual(args[0], self.mock_question)  # Question
        self.assertEqual(len(args[3]), 2)  # Events list (1 guess + 1 powerup)

        # Verify Simulator Run
        mock_sim_instance.run.assert_called_once_with(apply_end_of_day=False)

        # Verify State Restoration to PowerUpManager
        # We need to check if restore_daily_state was called on the powerup manager
        # Since managers['powerup'] is a real object, we can mock its method or check side effects.
        # Here we'll mock the manager itself for easier verification.
        self.game_runner.managers["powerup"] = MagicMock()

        # Re-run to trigger the mock manager
        self.game_runner.restore_game_state()
        self.game_runner.managers["powerup"].restore_daily_state.assert_called_with(
            "p1", {"shield_active": True}
        )

    @patch("src.core.game_runner.DailyGameSimulator")
    def test_restore_game_state_falls_back_to_all_players_when_no_snapshot(
        self, MockSimulator
    ):
        """When no snapshot exists, restore_game_state falls back to get_all_players."""
        self.mock_data_manager.get_daily_snapshot.return_value = (
            None  # None = no snapshot
        )
        all_players = {"p1": Player(id="p1", name="P1", score=100, answer_streak=5)}
        self.mock_data_manager.get_all_players.return_value = all_players
        self.mock_data_manager.get_guesses_for_daily_question.return_value = []
        self.mock_data_manager.get_powerup_usages_for_question.return_value = []
        MockSimulator.return_value.daily_state = {}

        self.game_runner.restore_game_state()

        # Snapshot tried first, then fallback to get_all_players
        self.mock_data_manager.get_daily_snapshot.assert_called_with(123)
        self.mock_data_manager.get_all_players.assert_called_once()

    def test_restore_game_state_uses_snapshot_for_steal_preload(self):
        """
        Regression: after a bot restart, restore_game_state must use the pre-hydration
        snapshot (not current players) so that steal_preload events are replayed with the
        original streak.  When the post-deduction streak is 0, apply_steal silently bails
        out and stealing_from is never set — the steal is lost and powerup_used_today
        stays False, letting the thief use a second power-up.
        """
        from src.core.powerup import PowerUpManager
        from src.core.player_manager import PlayerManager
        from src.cfg.main import ConfigReader

        cfg = MagicMock(spec=ConfigReader)
        cfg.get.return_value = "3"  # steal_streak_cost

        player_manager = MagicMock(spec=PlayerManager)
        data_manager = MagicMock()

        pum = PowerUpManager(player_manager, data_manager, config=cfg)
        self.game_runner.managers["powerup"] = pum

        steal_streak_cost = 3
        original_streak = steal_streak_cost  # thief had exactly the cost in streak days
        post_deduction_streak = 0  # hydration already zeroed it out

        # Snapshot reflects state BEFORE hydration (pre-deduction)
        snapshot = {
            "thief": Player(
                id="thief", name="Thief", score=1000, answer_streak=original_streak
            ),
            "target": Player(id="target", name="Target", score=2000, answer_streak=5),
        }
        self.mock_data_manager.get_daily_snapshot.return_value = snapshot

        # current players would have post-deduction streak (the buggy path)
        current_players = {
            "thief": Player(
                id="thief",
                name="Thief",
                score=1000,
                answer_streak=post_deduction_streak,
            ),
            "target": Player(id="target", name="Target", score=2000, answer_streak=5),
        }
        self.mock_data_manager.get_all_players.return_value = current_players

        # Events: steal_preload (overnight) then target answers correctly
        self.mock_data_manager.get_guesses_for_daily_question.return_value = [
            {
                "guessed_at": "2023-01-01 10:05:00",
                "player_id": "target",
                "guess_text": "A",
            }
        ]
        self.mock_data_manager.get_powerup_usages_for_question.return_value = [
            {
                "used_at": "2023-01-01 10:00:00",
                "user_id": "thief",
                "powerup_type": "steal_preload",
                "target_user_id": "target",
            }
        ]
        self.mock_data_manager.get_alternative_answers.return_value = []
        self.mock_data_manager.get_hint_sent_timestamp.return_value = None

        self.game_runner.restore_game_state()

        # With the snapshot (pre-deduction streak=3), apply_steal should correctly set
        # stealing_from — powerup_used_today must be True so no second steal is possible.
        thief_state = pum.daily_state.get("thief")
        self.assertIsNotNone(thief_state, "Thief state should be in daily_state")
        self.assertEqual(
            thief_state.stealing_from,
            "target",
            "stealing_from must be set after restore; with post-deduction streak=0 "
            "the old code silently dropped the steal and left powerup_used_today=False",
        )
        self.assertTrue(
            thief_state.powerup_used_today,
            "powerup_used_today must be True after overnight steal is restored",
        )

    def test_fetch_daily_events_parsing(self):
        """Test that _fetch_daily_events correctly parses DB records into Event objects."""
        self.mock_data_manager.get_guesses_for_daily_question.return_value = [
            {"guessed_at": "2023-01-01 10:00:00", "player_id": "p1", "guess_text": "A"}
        ]
        self.mock_data_manager.get_powerup_usages_for_question.return_value = [
            {
                "used_at": "2023-01-01 09:00:00",
                "user_id": "p2",
                "powerup_type": "steal",
                "target_user_id": "p1",
            }
        ]

        events = self.game_runner._fetch_daily_events(123)

        self.assertEqual(len(events), 2)

        # Check Guess Event
        guess_event = next(e for e in events if isinstance(e, GuessEvent))
        self.assertEqual(guess_event.user_id, "p1")
        self.assertEqual(guess_event.guess_text, "A")
        self.assertIsInstance(guess_event.timestamp, datetime)

        # Check PowerUp Event (Steal)
        powerup_event = next(e for e in events if isinstance(e, PowerUpEvent))
        self.assertEqual(powerup_event.user_id, "p2")
        self.assertEqual(powerup_event.powerup_type, "steal")
        self.assertEqual(powerup_event.target_user_id, "p1")
        self.assertIsInstance(powerup_event.timestamp, datetime)
