import unittest
from unittest.mock import patch, mock_open
from data.readers.tsv import (
    parse_value,
    read_jeopardy_questions,
    get_random_question,
    read_knowledge_bowl_questions,
)
from data.readers.question import Question


class TestTsv(unittest.TestCase):
    def test_parse_value(self):
        self.assertEqual(parse_value("$1,000"), 1000)
        self.assertEqual(parse_value("2,500"), 2500)
        self.assertEqual(parse_value("$2,500"), 2500)
        self.assertEqual(parse_value("500"), 500)
        self.assertEqual(parse_value(""), 0)
        self.assertEqual(parse_value(None), 0)

    def test_read_jeopardy_questions(self):
        """Test difficulty-based Jeopardy question reading."""
        # Mock TSV data with a complete category (5 questions)
        mock_data = (
            "category\tclue_value\tanswer\tquestion\tround\tair_date\tdaily_double_value\n"
            "HISTORY\t200\tQ1\tWhat is 1215?\t1\t2023-01-01\t0\n"
            "HISTORY\t400\tQ2\tWhat is the year?\t1\t2023-01-01\t0\n"
            "HISTORY\t600\tQ3\tWhat is answer 3?\t1\t2023-01-01\t0\n"
            "HISTORY\t800\tQ4\tWhat is answer 4?\t1\t2023-01-01\t0\n"
            "HISTORY\t1000\tQ5\tWhat is answer 5?\t1\t2023-01-01\t0\n"
            "SCIENCE\t200\tQ6\tWhat is Oxygen?\t1\t2023-01-01\t0\n"
            "SCIENCE\t400\tQ7\tWhat is 8?\t1\t2023-01-01\t0\n"
            "SCIENCE\t600\tQ8\tWhat is carbon?\t1\t2023-01-01\t0\n"
            "SCIENCE\t800\tQ9\tWhat is nitrogen?\t1\t2023-01-01\t0\n"
            "SCIENCE\t1000\tQ10\tWhat is helium?\t1\t2023-01-01\t0\n"
        )

        with patch("builtins.open", mock_open(read_data=mock_data)):
            # Test easy difficulty (positions 1-2)
            easy_questions = read_jeopardy_questions(
                "dummy_path.tsv", difficulty="easy"
            )
            self.assertEqual(len(easy_questions), 4)  # 2 categories × 2 positions
            self.assertTrue(all(q.clue_value == 200 for q in easy_questions))

            # Test medium difficulty (positions 3-4)
            medium_questions = read_jeopardy_questions(
                "dummy_path.tsv", difficulty="medium"
            )
            self.assertEqual(len(medium_questions), 4)  # 2 categories × 2 positions
            self.assertTrue(all(q.clue_value == 200 for q in medium_questions))

            # Test hard difficulty (position 5)
            hard_questions = read_jeopardy_questions(
                "dummy_path.tsv", difficulty="hard"
            )
            self.assertEqual(len(hard_questions), 2)  # 2 categories × 1 position
            self.assertTrue(all(q.clue_value == 300 for q in hard_questions))

    def test_read_jeopardy_questions_file_not_found(self):
        with patch("builtins.open", side_effect=FileNotFoundError):
            questions = read_jeopardy_questions("non_existent_path.tsv")
            self.assertEqual(questions, [])

    def test_read_jeopardy_questions_exception(self):
        with patch("builtins.open", side_effect=Exception("Test error")):
            questions = read_jeopardy_questions("any_path.tsv")
            self.assertEqual(questions, [])

    def test_get_random_question(self):
        q1 = Question(question="q1", answer="a1", category="cat1", clue_value=100)
        q2 = Question(question="q2", answer="a2", category="cat2", clue_value=200)
        questions = [q1, q2]

        random_question = get_random_question(questions)
        self.assertIn(random_question, questions)

        # Test with empty list
        self.assertIsNone(get_random_question([]))

        # Test with None
        self.assertIsNone(get_random_question(None))

    def test_read_knowledge_bowl_questions(self):
        mock_data = (
            "Number\tSubject\tQuestion\tAnswer\n"
            "1\t10.General\tWhat is the capital of France?\tParis\n"
            "2\tHistory\tWho was the first US president?\tGeorge Washington\n"
            "3\t20.Science\tWhat is H2O?\tWater\n"
            "4\tABC.NotANumber\tWhat is the sky color?\tBlue\n"
        )
        with patch("builtins.open", mock_open(read_data=mock_data)):
            questions = read_knowledge_bowl_questions("dummy_path.tsv")
            self.assertEqual(len(questions), 4)

            # Test first question (with digit prefix)
            q1 = questions[0]
            self.assertIsInstance(q1, Question)
            self.assertEqual(q1.question, "What is the capital of France?")
            self.assertEqual(q1.answer, "Paris")
            self.assertEqual(q1.category, "General")
            self.assertEqual(q1.clue_value, 10)
            self.assertEqual(q1.data_source, "Knowledge Bowl")
            self.assertEqual(q1.metadata["number"], "1")

            # Test second question (no dot in subject)
            q2 = questions[1]
            self.assertEqual(q2.category, "History")
            self.assertEqual(q2.clue_value, 0)

            # Test third question (with digit prefix)
            q3 = questions[2]
            self.assertEqual(q3.category, "Science")
            self.assertEqual(q3.clue_value, 20)

            # Test fourth question (dot in subject but not a digit prefix)
            q4 = questions[3]
            self.assertEqual(q4.category, "ABC.NotANumber")
            self.assertEqual(q4.clue_value, 0)

    def test_read_knowledge_bowl_questions_file_not_found(self):
        with patch("builtins.open", side_effect=FileNotFoundError):
            questions = read_knowledge_bowl_questions("non_existent_path.tsv")
            self.assertEqual(questions, [])

    def test_read_knowledge_bowl_questions_exception(self):
        with patch("builtins.open", side_effect=Exception("Test error")):
            questions = read_knowledge_bowl_questions("any_path.tsv")
            self.assertEqual(questions, [])


if __name__ == "__main__":
    unittest.main()
