import unittest
from unittest.mock import patch, mock_open
from data.readers.tsv import read_jeopardy_questions
from data.readers.question import Question


class TestJeopardyDifficultyFiltering(unittest.TestCase):
    """
    Tests for the new difficulty-based Jeopardy question filtering.
    Tests Easy, Medium, and Hard difficulty levels based on question position
    within each category.
    """

    def setUp(self):
        """Set up mock TSV data with multiple categories and rounds."""
        # Create a dataset with:
        # - 2 complete categories (5 questions each) in Round 1 (old point scale: 100-500)
        # - 2 complete categories (5 questions each) in Round 2 (old point scale: 200-1000)
        # - 2 complete categories (5 questions each) in Round 1 (new point scale: 200-1000)
        # - 2 complete categories (5 questions each) in Round 2 (new point scale: 400-2000)
        # - 2 Final Jeopardy questions
        self.mock_data = (
            "category\tclue_value\tanswer\tquestion\tround\tair_date\tdaily_double_value\n"
            # Round 1, Category 1 (old scale: 100-500)
            "HISTORY\t100\tQ1-Pos1\tA1\t1\t1984-09-10\t0\n"
            "HISTORY\t200\tQ2-Pos2\tA2\t1\t1984-09-10\t0\n"
            "HISTORY\t300\tQ3-Pos3\tA3\t1\t1984-09-10\t0\n"
            "HISTORY\t400\tQ4-Pos4\tA4\t1\t1984-09-10\t0\n"
            "HISTORY\t500\tQ5-Pos5\tA5\t1\t1984-09-10\t0\n"
            # Round 1, Category 2 (old scale: 100-500)
            "SCIENCE\t100\tQ6-Pos1\tA6\t1\t1984-09-10\t0\n"
            "SCIENCE\t200\tQ7-Pos2\tA7\t1\t1984-09-10\t0\n"
            "SCIENCE\t300\tQ8-Pos3\tA8\t1\t1984-09-10\t0\n"
            "SCIENCE\t400\tQ9-Pos4\tA9\t1\t1984-09-10\t0\n"
            "SCIENCE\t500\tQ10-Pos5\tA10\t1\t1984-09-10\t0\n"
            # Round 2, Category 1 (old scale: 200-1000)
            "GEOGRAPHY\t200\tQ11-Pos1\tA11\t2\t1984-09-10\t0\n"
            "GEOGRAPHY\t400\tQ12-Pos2\tA12\t2\t1984-09-10\t0\n"
            "GEOGRAPHY\t600\tQ13-Pos3\tA13\t2\t1984-09-10\t0\n"
            "GEOGRAPHY\t800\tQ14-Pos4\tA14\t2\t1984-09-10\t0\n"
            "GEOGRAPHY\t1000\tQ15-Pos5\tA15\t2\t1984-09-10\t0\n"
            # Round 2, Category 2 (old scale: 200-1000)
            "LITERATURE\t200\tQ16-Pos1\tA16\t2\t1984-09-10\t0\n"
            "LITERATURE\t400\tQ17-Pos2\tA17\t2\t1984-09-10\t0\n"
            "LITERATURE\t600\tQ18-Pos3\tA18\t2\t1984-09-10\t0\n"
            "LITERATURE\t800\tQ19-Pos4\tA19\t2\t1984-09-10\t0\n"
            "LITERATURE\t1000\tQ20-Pos5\tA20\t2\t1984-09-10\t0\n"
            # Round 1, Category 3 (new scale: 200-1000)
            "ARTS\t200\tQ21-Pos1\tA21\t1\t2020-01-15\t0\n"
            "ARTS\t400\tQ22-Pos2\tA22\t1\t2020-01-15\t0\n"
            "ARTS\t600\tQ23-Pos3\tA23\t1\t2020-01-15\t0\n"
            "ARTS\t800\tQ24-Pos4\tA24\t1\t2020-01-15\t0\n"
            "ARTS\t1000\tQ25-Pos5\tA25\t1\t2020-01-15\t0\n"
            # Round 1, Category 4 (new scale: 200-1000)
            "SPORTS\t200\tQ26-Pos1\tA26\t1\t2020-01-15\t0\n"
            "SPORTS\t400\tQ27-Pos2\tA27\t1\t2020-01-15\t0\n"
            "SPORTS\t600\tQ28-Pos3\tA28\t1\t2020-01-15\t0\n"
            "SPORTS\t800\tQ29-Pos4\tA29\t1\t2020-01-15\t0\n"
            "SPORTS\t1000\tQ30-Pos5\tA30\t1\t2020-01-15\t0\n"
            # Round 2, Category 3 (new scale: 400-2000)
            "MUSIC\t400\tQ31-Pos1\tA31\t2\t2020-01-15\t0\n"
            "MUSIC\t800\tQ32-Pos2\tA32\t2\t2020-01-15\t0\n"
            "MUSIC\t1200\tQ33-Pos3\tA33\t2\t2020-01-15\t0\n"
            "MUSIC\t1600\tQ34-Pos4\tA34\t2\t2020-01-15\t0\n"
            "MUSIC\t2000\tQ35-Pos5\tA35\t2\t2020-01-15\t0\n"
            # Round 2, Category 4 (new scale: 400-2000)
            "TECHNOLOGY\t400\tQ36-Pos1\tA36\t2\t2020-01-15\t0\n"
            "TECHNOLOGY\t800\tQ37-Pos2\tA37\t2\t2020-01-15\t0\n"
            "TECHNOLOGY\t1200\tQ38-Pos3\tA38\t2\t2020-01-15\t0\n"
            "TECHNOLOGY\t1600\tQ39-Pos4\tA39\t2\t2020-01-15\t0\n"
            "TECHNOLOGY\t2000\tQ40-Pos5\tA40\t2\t2020-01-15\t0\n"
            # Final Jeopardy questions
            "FINAL CATEGORY 1\t0\tFinal-Q1\tFinal-A1\tFinal Jeopardy!\t1984-09-10\t0\n"
            "FINAL CATEGORY 2\t0\tFinal-Q2\tFinal-A2\tFinal Jeopardy!\t2020-01-15\t0\n"
        )

    def test_easy_difficulty_returns_positions_1_and_2(self):
        """Test that 'easy' difficulty returns only positions 1 and 2 from each category."""
        with patch("builtins.open", mock_open(read_data=self.mock_data)):
            questions = read_jeopardy_questions("dummy.tsv", difficulty="easy")

            # Should get positions 1-2 from 8 categories = 16 questions
            self.assertEqual(len(questions), 16)

            # All questions should have normalized clue_value of 100
            for q in questions:
                self.assertEqual(
                    q.clue_value,
                    200,
                    f"Easy question should have clue_value=200, got {q.clue_value} for {q.question}",
                )

            # Verify we got positions 1 and 2
            question_texts = [q.question for q in questions]
            self.assertIn("Q1-Pos1", question_texts)
            self.assertIn("Q2-Pos2", question_texts)
            self.assertIn("Q6-Pos1", question_texts)
            self.assertIn("Q7-Pos2", question_texts)

            # Verify we didn't get position 3, 4, or 5
            self.assertNotIn("Q3-Pos3", question_texts)
            self.assertNotIn("Q4-Pos4", question_texts)
            self.assertNotIn("Q5-Pos5", question_texts)

            # Verify we didn't get Final Jeopardy
            self.assertNotIn("Final-Q1", question_texts)
            self.assertNotIn("Final-Q2", question_texts)

    def test_medium_difficulty_returns_positions_3_and_4(self):
        """Test that 'medium' difficulty returns only positions 3 and 4 from each category."""
        with patch("builtins.open", mock_open(read_data=self.mock_data)):
            questions = read_jeopardy_questions("dummy.tsv", difficulty="medium")

            # Should get positions 3-4 from 8 categories = 16 questions
            self.assertEqual(len(questions), 16)

            # All questions should have normalized clue_value of 200
            for q in questions:
                self.assertEqual(
                    q.clue_value,
                    200,
                    f"Medium question should have clue_value=200, got {q.clue_value} for {q.question}",
                )

            # Verify we got positions 3 and 4
            question_texts = [q.question for q in questions]
            self.assertIn("Q3-Pos3", question_texts)
            self.assertIn("Q4-Pos4", question_texts)
            self.assertIn("Q8-Pos3", question_texts)
            self.assertIn("Q9-Pos4", question_texts)

            # Verify we didn't get positions 1, 2, or 5
            self.assertNotIn("Q1-Pos1", question_texts)
            self.assertNotIn("Q2-Pos2", question_texts)
            self.assertNotIn("Q5-Pos5", question_texts)

            # Verify we didn't get Final Jeopardy
            self.assertNotIn("Final-Q1", question_texts)

    def test_hard_difficulty_returns_position_5_and_final_jeopardy(self):
        """Test that 'hard' difficulty returns position 5 and all Final Jeopardy questions."""
        with patch("builtins.open", mock_open(read_data=self.mock_data)):
            questions = read_jeopardy_questions("dummy.tsv", difficulty="hard")

            # Should get position 5 from 8 categories (8) + 2 Final Jeopardy = 10 questions
            self.assertEqual(len(questions), 10)

            # All questions should have normalized clue_value of 300
            for q in questions:
                self.assertEqual(
                    q.clue_value,
                    300,
                    f"Hard question should have clue_value=300, got {q.clue_value} for {q.question}",
                )

            # Verify we got position 5 questions
            question_texts = [q.question for q in questions]
            self.assertIn("Q5-Pos5", question_texts)
            self.assertIn("Q10-Pos5", question_texts)
            self.assertIn("Q15-Pos5", question_texts)
            self.assertIn("Q20-Pos5", question_texts)

            # Verify we got Final Jeopardy questions
            self.assertIn("Final-Q1", question_texts)
            self.assertIn("Final-Q2", question_texts)

            # Verify we didn't get positions 1-4
            self.assertNotIn("Q1-Pos1", question_texts)
            self.assertNotIn("Q2-Pos2", question_texts)
            self.assertNotIn("Q3-Pos3", question_texts)
            self.assertNotIn("Q4-Pos4", question_texts)

    def test_difficulty_works_with_both_point_scales(self):
        """Test that difficulty filtering works regardless of old or new point scales."""
        with patch("builtins.open", mock_open(read_data=self.mock_data)):
            easy_questions = read_jeopardy_questions("dummy.tsv", difficulty="easy")
            hard_questions = read_jeopardy_questions("dummy.tsv", difficulty="hard")

            easy_texts = [q.question for q in easy_questions]
            hard_texts = [q.question for q in hard_questions]

            # Old scale (100-500): positions 1-2 should be in easy
            self.assertIn("Q1-Pos1", easy_texts)  # HISTORY, 100pt
            self.assertIn("Q2-Pos2", easy_texts)  # HISTORY, 200pt

            # New scale (200-1000): positions 1-2 should be in easy
            self.assertIn("Q21-Pos1", easy_texts)  # ARTS, 200pt
            self.assertIn("Q22-Pos2", easy_texts)  # ARTS, 400pt

            # Old scale: position 5 should be in hard
            self.assertIn("Q5-Pos5", hard_texts)  # HISTORY, 500pt

            # New scale: position 5 should be in hard
            self.assertIn("Q25-Pos5", hard_texts)  # ARTS, 1000pt

    def test_metadata_includes_position_and_original_clue_value(self):
        """Test that metadata includes position and original clue value."""
        with patch("builtins.open", mock_open(read_data=self.mock_data)):
            questions = read_jeopardy_questions("dummy.tsv", difficulty="easy")

            # Find a specific question
            q1 = next(q for q in questions if q.question == "Q1-Pos1")

            # Check metadata
            self.assertIn("position", q1.metadata)
            self.assertEqual(q1.metadata["position"], 1)

            self.assertIn("original_clue_value", q1.metadata)
            self.assertEqual(q1.metadata["original_clue_value"], "100")

            self.assertEqual(q1.metadata["round"], "1")
            self.assertEqual(q1.metadata["air_date"], "1984-09-10")

    def test_final_jeopardy_metadata(self):
        """Test that Final Jeopardy questions have correct metadata."""
        with patch("builtins.open", mock_open(read_data=self.mock_data)):
            questions = read_jeopardy_questions("dummy.tsv", difficulty="hard")

            # Find Final Jeopardy questions
            final_questions = [
                q for q in questions if q.metadata["round"] == "Final Jeopardy!"
            ]

            self.assertEqual(len(final_questions), 2)

            for q in final_questions:
                self.assertEqual(q.clue_value, 300)
                self.assertIn("original_clue_value", q.metadata)
                # Final Jeopardy questions don't have a position field
                self.assertNotIn("position", q.metadata)

    def test_same_category_different_episodes_treated_separately(self):
        """Test that same category on different air dates are treated as separate groups."""
        # Create data with same category on two different dates
        mock_data_same_category = (
            "category\tclue_value\tanswer\tquestion\tround\tair_date\tdaily_double_value\n"
            "HISTORY\t100\tEpisode1-Q1\tA1\t1\t1984-09-10\t0\n"
            "HISTORY\t200\tEpisode1-Q2\tA2\t1\t1984-09-10\t0\n"
            "HISTORY\t300\tEpisode1-Q3\tA3\t1\t1984-09-10\t0\n"
            "HISTORY\t400\tEpisode1-Q4\tA4\t1\t1984-09-10\t0\n"
            "HISTORY\t500\tEpisode1-Q5\tA5\t1\t1984-09-10\t0\n"
            "HISTORY\t100\tEpisode2-Q1\tA1\t1\t1984-09-11\t0\n"
            "HISTORY\t200\tEpisode2-Q2\tA2\t1\t1984-09-11\t0\n"
            "HISTORY\t300\tEpisode2-Q3\tA3\t1\t1984-09-11\t0\n"
            "HISTORY\t400\tEpisode2-Q4\tA4\t1\t1984-09-11\t0\n"
            "HISTORY\t500\tEpisode2-Q5\tA5\t1\t1984-09-11\t0\n"
        )

        with patch("builtins.open", mock_open(read_data=mock_data_same_category)):
            easy_questions = read_jeopardy_questions("dummy.tsv", difficulty="easy")

            # Should get positions 1-2 from both episodes = 4 questions
            self.assertEqual(len(easy_questions), 4)

            question_texts = [q.question for q in easy_questions]
            self.assertIn("Episode1-Q1", question_texts)
            self.assertIn("Episode1-Q2", question_texts)
            self.assertIn("Episode2-Q1", question_texts)
            self.assertIn("Episode2-Q2", question_texts)

    def test_same_category_different_rounds_treated_separately(self):
        """Test that same category in different rounds are treated as separate groups."""
        mock_data_same_category_rounds = (
            "category\tclue_value\tanswer\tquestion\tround\tair_date\tdaily_double_value\n"
            "HISTORY\t100\tRound1-Q1\tA1\t1\t1984-09-10\t0\n"
            "HISTORY\t200\tRound1-Q2\tA2\t1\t1984-09-10\t0\n"
            "HISTORY\t300\tRound1-Q3\tA3\t1\t1984-09-10\t0\n"
            "HISTORY\t400\tRound1-Q4\tA4\t1\t1984-09-10\t0\n"
            "HISTORY\t500\tRound1-Q5\tA5\t1\t1984-09-10\t0\n"
            "HISTORY\t200\tRound2-Q1\tA1\t2\t1984-09-10\t0\n"
            "HISTORY\t400\tRound2-Q2\tA2\t2\t1984-09-10\t0\n"
            "HISTORY\t600\tRound2-Q3\tA3\t2\t1984-09-10\t0\n"
            "HISTORY\t800\tRound2-Q4\tA4\t2\t1984-09-10\t0\n"
            "HISTORY\t1000\tRound2-Q5\tA5\t2\t1984-09-10\t0\n"
        )

        with patch(
            "builtins.open", mock_open(read_data=mock_data_same_category_rounds)
        ):
            easy_questions = read_jeopardy_questions("dummy.tsv", difficulty="easy")

            # Should get positions 1-2 from both rounds = 4 questions
            self.assertEqual(len(easy_questions), 4)

            question_texts = [q.question for q in easy_questions]
            self.assertIn("Round1-Q1", question_texts)
            self.assertIn("Round1-Q2", question_texts)
            self.assertIn("Round2-Q1", question_texts)
            self.assertIn("Round2-Q2", question_texts)

    def test_invalid_difficulty_defaults_to_easy(self):
        """Test that invalid difficulty parameter defaults to 'easy' with warning."""
        with patch("builtins.open", mock_open(read_data=self.mock_data)):
            questions = read_jeopardy_questions("dummy.tsv", difficulty="invalid")

            # Should default to easy (16 questions)
            self.assertEqual(len(questions), 16)

            # Should all have easy difficulty points
            for q in questions:
                self.assertEqual(q.clue_value, 200)

    def test_case_insensitive_difficulty(self):
        """Test that difficulty parameter is case-insensitive."""
        with patch("builtins.open", mock_open(read_data=self.mock_data)):
            questions_upper = read_jeopardy_questions("dummy.tsv", difficulty="EASY")
            questions_mixed = read_jeopardy_questions("dummy.tsv", difficulty="EaSy")
            questions_lower = read_jeopardy_questions("dummy.tsv", difficulty="easy")

            # All should return the same number of questions
            self.assertEqual(len(questions_upper), 16)
            self.assertEqual(len(questions_mixed), 16)
            self.assertEqual(len(questions_lower), 16)

    def test_category_with_fewer_than_5_questions(self):
        """Test handling of categories with fewer than 5 questions."""
        mock_data_incomplete = (
            "category\tclue_value\tanswer\tquestion\tround\tair_date\tdaily_double_value\n"
            "INCOMPLETE\t100\tQ1\tA1\t1\t1984-09-10\t0\n"
            "INCOMPLETE\t200\tQ2\tA2\t1\t1984-09-10\t0\n"
            "INCOMPLETE\t300\tQ3\tA3\t1\t1984-09-10\t0\n"
        )

        with patch("builtins.open", mock_open(read_data=mock_data_incomplete)):
            easy_questions = read_jeopardy_questions("dummy.tsv", difficulty="easy")
            medium_questions = read_jeopardy_questions("dummy.tsv", difficulty="medium")
            hard_questions = read_jeopardy_questions("dummy.tsv", difficulty="hard")

            # Easy should get positions 1-2 (2 questions)
            self.assertEqual(len(easy_questions), 2)

            # Medium should get position 3 (1 question - since we only have 3 total)
            self.assertEqual(len(medium_questions), 1)

            # Hard should get position 5, but we don't have it (0 questions)
            self.assertEqual(len(hard_questions), 0)

    def test_file_not_found_returns_empty_list(self):
        """Test that file not found returns empty list."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            questions = read_jeopardy_questions("nonexistent.tsv", difficulty="easy")
            self.assertEqual(questions, [])

    def test_general_exception_returns_empty_list(self):
        """Test that general exceptions return empty list."""
        with patch("builtins.open", side_effect=Exception("Test error")):
            questions = read_jeopardy_questions("any.tsv", difficulty="easy")
            self.assertEqual(questions, [])

    def test_category_formatting_includes_jeopardy_prefix(self):
        """Test that categories are formatted as 'Jeopardy! | CATEGORY'."""
        with patch("builtins.open", mock_open(read_data=self.mock_data)):
            # Test easy difficulty
            easy_questions = read_jeopardy_questions("dummy.tsv", difficulty="easy")
            for q in easy_questions:
                self.assertTrue(
                    q.category.startswith("Jeopardy! | "),
                    f"Category should start with 'Jeopardy! | ', got: {q.category}",
                )

            # Verify specific category format
            q1 = next(q for q in easy_questions if q.question == "Q1-Pos1")
            self.assertEqual(q1.category, "Jeopardy! | HISTORY")

            # Test medium difficulty
            medium_questions = read_jeopardy_questions("dummy.tsv", difficulty="medium")
            for q in medium_questions:
                self.assertTrue(
                    q.category.startswith("Jeopardy! | "),
                    f"Category should start with 'Jeopardy! | ', got: {q.category}",
                )

            # Test hard difficulty (regular questions)
            hard_questions = read_jeopardy_questions("dummy.tsv", difficulty="hard")
            regular_hard = [q for q in hard_questions if "Final" not in q.question]
            for q in regular_hard:
                self.assertTrue(
                    q.category.startswith("Jeopardy! | "),
                    f"Category should start with 'Jeopardy! | ', got: {q.category}",
                )

            # Test Final Jeopardy formatting
            final_jeopardy = [q for q in hard_questions if "Final" in q.question]
            for q in final_jeopardy:
                self.assertTrue(
                    q.category.startswith("Jeopardy! | "),
                    f"Final Jeopardy category should start with 'Jeopardy! | ', got: {q.category}",
                )

            # Verify specific Final Jeopardy category
            fj1 = next(q for q in final_jeopardy if q.question == "Final-Q1")
            self.assertEqual(fj1.category, "Jeopardy! | FINAL CATEGORY 1")


if __name__ == "__main__":
    unittest.main()
