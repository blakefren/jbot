import unittest
import os
import tempfile
from unittest.mock import patch, mock_open
from data.readers.csv_reader import (
    read_knowledge_bowl_questions,
    read_simple_questions,
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

    def tearDown(self):
        # Clean up the temporary directory and files
        if os.path.exists(self.knowledge_bowl_path):
            os.remove(self.knowledge_bowl_path)
        if os.path.exists(self.simple_path):
            os.remove(self.simple_path)
        if os.path.exists(self.temp_data_dir):
            os.rmdir(self.temp_data_dir)

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
        self.assertEqual(q1.category, "Simple Test")
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

    def test_read_simple_questions_with_hint(self):
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".csv") as f:
            f.write("Question,Answer,Hint\nWhat is 2+2?,4,Think of basic addition.\n")
            f.flush()
            questions = read_simple_questions(f.name, "TestSource")
            self.assertEqual(len(questions), 1)
            self.assertEqual(questions[0].question, "What is 2+2?")
            self.assertEqual(questions[0].answer, "4")
            self.assertEqual(questions[0].hint, "Think of basic addition.")
        os.unlink(f.name)

    def test_read_simple_questions_without_hint(self):
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".csv") as f:
            f.write("Question,Answer\nWhat is 2+2?,4\n")
            f.flush()
            questions = read_simple_questions(f.name, "TestSource")
            self.assertEqual(len(questions), 1)
            self.assertEqual(questions[0].question, "What is 2+2?")
            self.assertEqual(questions[0].answer, "4")
            self.assertIsNone(questions[0].hint)
        os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
