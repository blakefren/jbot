import unittest
from readers.question import Question


class TestQuestion(unittest.TestCase):
    def test_question_creation_valid(self):
        """Tests successful creation of a Question object with valid inputs."""
        q = Question(
            question="This is a question.",
            answer="This is an answer.",
            category="TESTING",
            clue_value=100,
            data_source="test_suite",
            metadata={"key": "value"},
        )
        self.assertEqual(q.question, "This is a question.")
        self.assertEqual(q.answer, "This is an answer.")
        self.assertEqual(q.category, "TESTING")
        self.assertEqual(q.clue_value, 100)
        self.assertEqual(q.data_source, "test_suite")
        self.assertEqual(q.metadata, {"key": "value"})
        self.assertIsNotNone(q.id)

    def test_question_creation_defaults(self):
        """Tests that default values are used when optional arguments are not provided."""
        q = Question(
            question="Another question.",
            answer="Another answer.",
            category="DEFAULTS",
            clue_value=200,
        )
        self.assertEqual(q.data_source, "unknown")
        self.assertEqual(q.metadata, {})

    def test_question_creation_invalid_input(self):
        """Tests that Question creation raises ValueError for invalid inputs."""
        with self.assertRaises(ValueError):
            Question(question="", answer="A", category="B", clue_value=100)
        with self.assertRaises(ValueError):
            Question(question="A", answer="", category="B", clue_value=100)
        with self.assertRaises(ValueError):
            Question(question="A", answer="B", category="", clue_value=100)
        with self.assertRaises(ValueError):
            Question(question="A", answer="B", category="C", clue_value=-100)

    def test_str_representation(self):
        """Tests the string representation of the Question object."""
        q = Question(question="Q", answer="A", category="C", clue_value=100)
        # We don't test the ID as it's a hash, but we check that it's in the string
        self.assertIn(f"ID: {q.id}", str(q))
        self.assertIn("Category: C", str(q))
        self.assertIn("Value: $100", str(q))
        self.assertIn("Question: Q", str(q))
        self.assertIn("Answer: A", str(q))
        self.assertIn("Source: unknown", str(q))

    def test_to_dict(self):
        """Tests the conversion of a Question object to a dictionary."""
        q = Question(
            question="Q",
            answer="A",
            category="C",
            clue_value=100,
            data_source="test",
            metadata={"foo": "bar"},
        )
        q_dict = q.to_dict()
        expected_dict = {
            "id": q.id,
            "question": "Q",
            "answer": "A",
            "category": "C",
            "clue_value": 100,
            "data_source": "test",
            "metadata": {"foo": "bar"},
        }
        self.assertEqual(q_dict, expected_dict)

    def test_get_metadata(self):
        """Tests the get_metadata method."""
        q = Question(
            question="Q",
            answer="A",
            category="C",
            clue_value=100,
            metadata={"key1": "value1"},
        )
        self.assertEqual(q.get_metadata("key1"), "value1")
        self.assertIsNone(q.get_metadata("key2"))
        self.assertEqual(q.get_metadata("key2", "default"), "default")

    def test_from_dict(self):
        """Tests the creation of a Question object from a dictionary."""
        q_data = {
            "question": "From Dict",
            "answer": "Is Correct",
            "category": "SERIALIZATION",
            "clue_value": 500,
            "data_source": "dict_source",
            "metadata": {"a": 1},
        }
        q = Question.from_dict(q_data)
        self.assertEqual(q.question, "From Dict")
        self.assertEqual(q.answer, "Is Correct")
        self.assertEqual(q.category, "SERIALIZATION")
        self.assertEqual(q.clue_value, 500)
        self.assertEqual(q.data_source, "dict_source")
        self.assertEqual(q.metadata, {"a": 1})

    def test_from_dict_with_defaults(self):
        """Tests creating from a dict with missing optional keys."""
        q_data = {
            "question": "From Dict",
            "answer": "Is Correct",
            "category": "SERIALIZATION",
            "clue_value": 500,
        }
        q = Question.from_dict(q_data)
        self.assertEqual(q.data_source, "unknown")
        self.assertEqual(q.metadata, {})


if __name__ == "__main__":
    unittest.main()
