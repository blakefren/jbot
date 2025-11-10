import unittest
import os
from unittest.mock import patch, mock_open
from data.readers.csv_reader import (
    read_riddle_questions,
    read_riddle_with_hints_questions,
    read_knowledge_bowl_questions,
    read_simple_questions,
    read_general_trivia_questions,
)
from data.readers.question import Question


class TestCsvReader(unittest.TestCase):
    def setUp(self):
        # Define paths for temporary test data
        self.temp_data_dir = os.path.join(os.path.dirname(__file__), "temp_data")
        os.makedirs(self.temp_data_dir, exist_ok=True)

        self.knowledge_bowl_path = os.path.join(
            self.temp_data_dir, "test_knowledge_bowl.csv"
        )
        with open(self.knowledge_bowl_path, "w", newline="") as f:
            f.write("Subject,Question,Answer\n")
            f.write("History,What year did WWII end?,1945\n")
            f.write("Science,What is the chemical symbol for water?,H2O\n")

        self.simple_path = os.path.join(self.temp_data_dir, "test_simple.csv")
        with open(self.simple_path, "w", newline="") as f:
            f.write("Question,Answer\n")
            f.write("What is 2+2?,4\n")
            f.write("What is the capital of France?,Paris\n")

        self.general_trivia_path = os.path.join(
            self.temp_data_dir, "test_general_trivia.csv"
        )
        with open(self.general_trivia_path, "w", newline="") as f:
            f.write("Category,Question,Answer\n")
            f.write("Math,What is 3*3?,9\n")
            f.write("Geography,What is the largest ocean?,Pacific\n")

    def tearDown(self):
        # Clean up the temporary directory and files
        if os.path.exists(self.knowledge_bowl_path):
            os.remove(self.knowledge_bowl_path)
        if os.path.exists(self.simple_path):
            os.remove(self.simple_path)
        if os.path.exists(self.general_trivia_path):
            os.remove(self.general_trivia_path)
        if os.path.exists(self.temp_data_dir):
            os.rmdir(self.temp_data_dir)

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

    def test_read_knowledge_bowl_questions(self):
        questions = read_knowledge_bowl_questions(self.knowledge_bowl_path)
        self.assertEqual(len(questions), 2)
        q1 = questions[0]
        self.assertEqual(q1.question, "What year did WWII end?")
        self.assertEqual(q1.answer, "1945")
        self.assertEqual(q1.category, "History")
        self.assertEqual(q1.data_source, "Knowledge Bowl")
        q2 = questions[1]
        self.assertEqual(q2.question, "What is the chemical symbol for water?")
        self.assertEqual(q2.answer, "H2O")
        self.assertEqual(q2.category, "Science")

    def test_read_knowledge_bowl_questions_file_not_found(self):
        with patch("builtins.open", side_effect=FileNotFoundError):
            questions = read_knowledge_bowl_questions("non_existent_path.csv")
            self.assertEqual(questions, [])

    def test_read_knowledge_bowl_questions_exception(self):
        with patch("builtins.open", side_effect=Exception("Test error")):
            questions = read_knowledge_bowl_questions("any_path.csv")
            self.assertEqual(questions, [])

    def test_read_simple_questions(self):
        questions = read_simple_questions(self.simple_path, "Simple Test")
        self.assertEqual(len(questions), 2)
        q1 = questions[0]
        self.assertEqual(q1.question, "What is 2+2?")
        self.assertEqual(q1.answer, "4")
        self.assertEqual(q1.category, "General")
        self.assertEqual(q1.data_source, "Simple Test")
        q2 = questions[1]
        self.assertEqual(q2.question, "What is the capital of France?")
        self.assertEqual(q2.answer, "Paris")

    def test_read_simple_questions_file_not_found(self):
        with patch("builtins.open", side_effect=FileNotFoundError):
            questions = read_simple_questions("non_existent_path.csv", "source")
            self.assertEqual(questions, [])

    def test_read_simple_questions_exception(self):
        with patch("builtins.open", side_effect=Exception("Test error")):
            questions = read_simple_questions("any_path.csv", "source")
            self.assertEqual(questions, [])

    def test_read_general_trivia_questions(self):
        questions = read_general_trivia_questions(self.general_trivia_path)
        self.assertEqual(len(questions), 2)
        q1 = questions[0]
        self.assertEqual(q1.question, "What is 3*3?")
        self.assertEqual(q1.answer, "9")
        self.assertEqual(q1.category, "Math")
        self.assertEqual(q1.data_source, "General Trivia")
        q2 = questions[1]
        self.assertEqual(q2.question, "What is the largest ocean?")
        self.assertEqual(q2.answer, "Pacific")
        self.assertEqual(q2.category, "Geography")

    def test_read_general_trivia_questions_file_not_found(self):
        with patch("builtins.open", side_effect=FileNotFoundError):
            questions = read_general_trivia_questions("non_existent_path.csv")
            self.assertEqual(questions, [])

    def test_read_general_trivia_questions_exception(self):
        with patch("builtins.open", side_effect=Exception("Test error")):
            questions = read_general_trivia_questions("any_path.csv")
            self.assertEqual(questions, [])


if __name__ == "__main__":
    unittest.main()
