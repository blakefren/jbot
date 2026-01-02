import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
from src.core.game_runner import GameRunner
from src.core.events import GuessEvent, PowerUpEvent
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

        # Mock DataManager returns
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

    def test_fetch_daily_events_parsing(self):
        """Test that _fetch_daily_events correctly parses DB records into Event objects."""
        self.mock_data_manager.get_guesses_for_daily_question.return_value = [
            {"guessed_at": "2023-01-01 10:00:00", "player_id": "p1", "guess_text": "A"}
        ]
        self.mock_data_manager.get_powerup_usages_for_question.return_value = [
            {
                "used_at": "2023-01-01 09:00:00",
                "user_id": "p2",
                "powerup_type": "wager",
                "target_user_id": "50",
            }
        ]

        events = self.game_runner._fetch_daily_events(123)

        self.assertEqual(len(events), 2)

        # Check Guess Event
        guess_event = next(e for e in events if isinstance(e, GuessEvent))
        self.assertEqual(guess_event.user_id, "p1")
        self.assertEqual(guess_event.guess_text, "A")
        self.assertIsInstance(guess_event.timestamp, datetime)

        # Check PowerUp Event (Wager)
        powerup_event = next(e for e in events if isinstance(e, PowerUpEvent))
        self.assertEqual(powerup_event.user_id, "p2")
        self.assertEqual(powerup_event.powerup_type, "wager")
        self.assertEqual(powerup_event.amount, 50)  # Parsed from target_user_id
        self.assertIsInstance(powerup_event.timestamp, datetime)
