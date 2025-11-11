import unittest
from unittest.mock import MagicMock
from datetime import date

from src.core.data_manager import DataManager
from data.readers.question import Question


class TestDataManager(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.data_manager = DataManager(self.mock_db)

    def test_log_daily_question_force_new(self):
        # Arrange
        question = Question("q", "a", "c", 100)
        question.id = "hash123"
        today = date.today()

        # Mock that a daily question already exists
        self.data_manager.get_todays_daily_question = MagicMock(
            return_value=(question, 1)
        )
        self.mock_db.execute_query.return_value = [
            {"id": 1}
        ]  # Existing question in questions table

        # Act
        daily_question_id = self.data_manager.log_daily_question(
            question, force_new=True
        )

        # Assert
        self.mock_db.execute_update.assert_called_with(
            "UPDATE daily_questions SET question_id = ? WHERE sent_at = ?", (1, today)
        )
        self.assertEqual(daily_question_id, 1)

    def test_log_daily_question_force_new_no_existing(self):
        # Arrange
        question = Question("q", "a", "c", 100)
        question.id = "hash123"
        today = date.today()

        # Mock that no daily question exists
        self.data_manager.get_todays_daily_question = MagicMock(return_value=None)
        self.mock_db.execute_query.return_value = [{"id": 1}]
        self.mock_db.execute_update.return_value = (None, 2)  # New daily_question_id

        # Act
        daily_question_id = self.data_manager.log_daily_question(
            question, force_new=True
        )

        # Assert
        self.mock_db.execute_update.assert_any_call(
            "INSERT INTO daily_questions (question_id, sent_at) VALUES (?, ?)",
            (1, today),
        )
        self.assertEqual(daily_question_id, 2)


if __name__ == "__main__":
    unittest.main()
