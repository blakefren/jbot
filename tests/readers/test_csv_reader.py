import unittest
from unittest.mock import patch, mock_open
from readers.csv_reader import read_riddle_questions
from readers.question import Question

class TestCsvReader(unittest.TestCase):

    def test_read_riddle_questions(self):
        mock_data = (
            'QUESTIONS,ANSWERS\n'
            '"Almost everyone needs it, asks for it, gives it. But almost nobody takes it.",advice\n'
            'What goes up but never comes down?,age\n'
        )
        with patch("builtins.open", mock_open(read_data=mock_data)):
            questions = read_riddle_questions("dummy_path.csv")
            self.assertEqual(len(questions), 2)

            q1 = questions[0]
            self.assertIsInstance(q1, Question)
            self.assertEqual(q1.question, "Almost everyone needs it, asks for it, gives it. But almost nobody takes it.")
            self.assertEqual(q1.answer, "advice")
            self.assertEqual(q1.category, "Riddle")
            self.assertEqual(q1.clue_value, 100)
            self.assertEqual(q1.data_source, "Riddles (small)")

            q2 = questions[1]
            self.assertEqual(q2.question, "What goes up but never comes down?")
            self.assertEqual(q2.answer, "age")

    def test_read_riddle_questions_file_not_found(self):
        with patch("builtins.open", side_effect=FileNotFoundError):
            questions = read_riddle_questions("non_existent_path.csv")
            self.assertEqual(questions, [])

    def test_read_riddle_questions_exception(self):
        with patch("builtins.open", side_effect=Exception("Test error")):
            questions = read_riddle_questions("any_path.csv")
            self.assertEqual(questions, [])

if __name__ == "__main__":
    unittest.main()
