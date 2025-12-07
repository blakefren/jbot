import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock
from src.core.data_manager import DataManager
from src.core.guess_handler import GuessHandler
from src.core.player_manager import PlayerManager
from data.readers.question import Question
from db.database import Database


class TestSkipLogic(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.data_manager = DataManager(self.db)
        self.data_manager.initialize_database()
        self.player_manager = PlayerManager(self.data_manager)

        # Create a player
        self.player_id = "123"
        self.player_name = "TestPlayer"
        self.player_manager.get_or_create_player(self.player_id, self.player_name)

    def tearDown(self):
        self.db.close()

    def test_log_daily_question_force_new(self):
        # Log first question
        q1 = Question(
            question="Q1",
            answer="A1",
            category="C",
            clue_value=100,
            data_source="test",
            hint="h1",
        )
        dq_id1 = self.data_manager.log_daily_question(q1)

        # Log second question with force_new=True (Skip)
        q2 = Question(
            question="Q2",
            answer="A2",
            category="C",
            clue_value=100,
            data_source="test",
            hint="h2",
        )
        dq_id2 = self.data_manager.log_daily_question(q2, force_new=True)

        self.assertNotEqual(dq_id1, dq_id2)

        # Verify today's daily question is the new one
        today_q, today_dq_id = self.data_manager.get_todays_daily_question()
        self.assertEqual(today_dq_id, dq_id2)
        self.assertEqual(today_q.question, "Q2")

    def test_guess_handler_streak_preservation_on_skip(self):
        # 1. Set up Q1
        q1 = Question(
            question="Q1",
            answer="A1",
            category="C",
            clue_value=100,
            data_source="test",
            hint="h1",
        )
        dq_id1 = self.data_manager.log_daily_question(q1)

        # 2. Player answers Q1 correctly
        gh1 = GuessHandler(self.data_manager, self.player_manager, q1, dq_id1, {})
        is_correct, _, _, _ = gh1.handle_guess(
            int(self.player_id), self.player_name, "A1"
        )
        self.assertTrue(is_correct)

        # Verify streak is 1
        player = self.player_manager.get_player(self.player_id)
        self.assertEqual(player.answer_streak, 1)

        # 3. Skip to Q2
        q2 = Question(
            question="Q2",
            answer="A2",
            category="C",
            clue_value=100,
            data_source="test",
            hint="h2",
        )
        dq_id2 = self.data_manager.log_daily_question(q2, force_new=True)

        # 4. Player answers Q2 correctly
        gh2 = GuessHandler(self.data_manager, self.player_manager, q2, dq_id2, {})
        is_correct, _, _, _ = gh2.handle_guess(
            int(self.player_id), self.player_name, "A2"
        )
        self.assertTrue(is_correct)

        # Verify streak is still 1 (not reset, not double incremented)
        player = self.player_manager.get_player(self.player_id)
        self.assertEqual(player.answer_streak, 1)

    def test_guess_handler_guess_count_reset_on_skip(self):
        # 1. Set up Q1
        q1 = Question(
            question="Q1",
            answer="A1",
            category="C",
            clue_value=100,
            data_source="test",
            hint="h1",
        )
        dq_id1 = self.data_manager.log_daily_question(q1)

        # 2. Player guesses incorrectly on Q1
        gh1 = GuessHandler(self.data_manager, self.player_manager, q1, dq_id1, {})
        gh1.handle_guess(int(self.player_id), self.player_name, "Wrong1")

        guesses = gh1.get_player_guesses(int(self.player_id))
        self.assertEqual(len(guesses), 1)

        # 3. Skip to Q2
        q2 = Question(
            question="Q2",
            answer="A2",
            category="C",
            clue_value=100,
            data_source="test",
            hint="h2",
        )
        dq_id2 = self.data_manager.log_daily_question(q2, force_new=True)

        # 4. Check guesses for Q2 (should be empty)
        gh2 = GuessHandler(self.data_manager, self.player_manager, q2, dq_id2, {})
        guesses = gh2.get_player_guesses(int(self.player_id))
        self.assertEqual(len(guesses), 0)


if __name__ == "__main__":
    unittest.main()
