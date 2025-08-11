import unittest
from unittest.mock import patch, mock_open
from readers.tsv import parse_value, read_jeopardy_questions, get_random_question, read_knowledge_bowl_questions
from readers.question import Question


class TestTsv(unittest.TestCase):

    def test_parse_value(self):
        self.assertEqual(parse_value("$1,000"), 1000)
        self.assertEqual(parse_value("2,500"), 2500)
        self.assertEqual(parse_value("$2,500"), 2500)
        self.assertEqual(parse_value("500"), 500)
        self.assertEqual(parse_value(""), 0)
        self.assertEqual(parse_value(None), 0)

    def test_read_jeopardy_questions(self):
        # Mock TSV data
        mock_data = (
            "category\tclue_value\tquestion\tanswer\tround\tair_date\tdaily_double_value\n"
            "HISTORY\t$200\tThe year the Magna Carta was signed\tWhat is 1215?\t1\t2023-01-01\t0\n"
            "SCIENCE\t$400\tThe atomic number of Oxygen\tWhat is 8?\t1\t2023-01-01\t0\n"
            "FINAL\t$2000\tThe only planet that rotates clockwise\tWhat is Venus?\t3\t2023-01-01\t0\n"
        )

        with patch("builtins.open", mock_open(read_data=mock_data)):
            questions = read_jeopardy_questions(
                "dummy_path.tsv", final_jeopardy_score=2000
            )
            self.assertEqual(len(questions), 3)

            # Test first question
            self.assertIsInstance(questions[0], Question)
            self.assertEqual(questions[0].category, "HISTORY")
            self.assertEqual(questions[0].clue_value, 200)
            self.assertEqual(
                questions[0].question, "What is 1215?"
            )
            self.assertEqual(questions[0].answer, "The year the Magna Carta was signed")
            self.assertEqual(questions[0].data_source, "Jeopardy!")
            self.assertEqual(questions[0].metadata["round"], "1")

            # Test final jeopardy question
            self.assertEqual(questions[2].category, "FINAL")
            self.assertEqual(questions[2].clue_value, 2000)
            self.assertEqual(questions[2].metadata["round"], "3")

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
        )
        with patch("builtins.open", mock_open(read_data=mock_data)):
            questions = read_knowledge_bowl_questions("dummy_path.tsv")
            self.assertEqual(len(questions), 3)

            # Test first question
            q1 = questions[0]
            self.assertIsInstance(q1, Question)
            self.assertEqual(q1.question, "What is the capital of France?")
            self.assertEqual(q1.answer, "Paris")
            self.assertEqual(q1.category, "General")
            self.assertEqual(q1.clue_value, 10)
            self.assertEqual(q1.data_source, "Knowledge Bowl")
            self.assertEqual(q1.metadata["number"], "1")

            # Test second question
            q2 = questions[1]
            self.assertEqual(q2.category, "History")
            self.assertEqual(q2.clue_value, 0)

            # Test third question
            q3 = questions[2]
            self.assertEqual(q3.category, "Science")
            self.assertEqual(q3.clue_value, 20)

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
