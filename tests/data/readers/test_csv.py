import unittest
from unittest.mock import patch, mock_open
from data.readers.csv_reader import read_riddle_questions, read_riddle_with_hints_questions
from data.readers.question import Question


class TestCsvReader(unittest.TestCase):

    def test_read_riddle_questions(self):
        mock_data = (
            "QUESTIONS,ANSWERS\n"
            '"Almost everyone needs it, asks for it, gives it. But almost nobody takes it.",advice\n'
            "What goes up but never comes down?,age\n"
        )
        with patch("builtins.open", mock_open(read_data=mock_data)):
            questions = read_riddle_questions("dummy_path.csv")
            self.assertEqual(len(questions), 2)

            q1 = questions[0]
            self.assertIsInstance(q1, Question)
            self.assertEqual(
                q1.question,
                "Almost everyone needs it, asks for it, gives it. But almost nobody takes it.",
            )
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

    def test_read_riddle_with_hints_questions(self):
        mock_data = (
            "Riddle,Answer,Hint\n"
            '"I speak without a mouth and hear without ears. I have no body, but I come alive with the wind. What am I?",An echo,Think about a sound that repeats itself in nature\n'
            '"The more you take, the more you leave behind. What am I?",Footsteps,Consider what you create as you walk along a beach\n'
        )
        with patch("builtins.open", mock_open(read_data=mock_data)):
            questions = read_riddle_with_hints_questions("dummy_path.csv")
            self.assertEqual(len(questions), 2)

            q1 = questions[0]
            self.assertIsInstance(q1, Question)
            self.assertEqual(
                q1.question,
                "I speak without a mouth and hear without ears. I have no body, but I come alive with the wind. What am I?",
            )
            self.assertEqual(q1.answer, "An echo")
            self.assertEqual(q1.category, "Riddle")
            self.assertEqual(q1.clue_value, 100)
            self.assertEqual(q1.data_source, "Riddles with Hints")
            self.assertEqual(
                q1.hint, "Think about a sound that repeats itself in nature"
            )

            q2 = questions[1]
            self.assertEqual(
                q2.question, "The more you take, the more you leave behind. What am I?"
            )
            self.assertEqual(q2.answer, "Footsteps")
            self.assertEqual(
                q2.hint, "Consider what you create as you walk along a beach"
            )

    def test_read_riddle_with_hints_questions_file_not_found(self):
        with patch("builtins.open", side_effect=FileNotFoundError):
            questions = read_riddle_with_hints_questions("non_existent_path.csv")
            self.assertEqual(questions, [])

    def test_read_riddle_with_hints_questions_exception(self):
        with patch("builtins.open", side_effect=Exception("Test error")):
            questions = read_riddle_with_hints_questions("any_path.csv")
            self.assertEqual(questions, [])


if __name__ == "__main__":
    unittest.main()
