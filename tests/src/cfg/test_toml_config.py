import unittest
import os
import tempfile
from unittest.mock import patch, MagicMock
from src.cfg.main import ConfigReader


class TestTomlConfiguration(unittest.TestCase):
    """Tests for TOML configuration loading and dataset path resolution."""

    def setUp(self):
        """Create a temporary TOML config for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_dir = os.path.join(self.temp_dir, "config")
        os.makedirs(self.config_dir)

        self.sources_toml = os.path.join(self.config_dir, "sources.toml")
        with open(self.sources_toml, "w") as f:
            f.write("""
[datasets]
jeopardy = "datasets/jeopardy.tsv"
knowledge_bowl = "datasets/kb.csv"
5th_grader = "datasets/5th_grader.csv"

[[source]]
name = "5th_grader"
type = "file"
dataset = "5th_grader"
weight = 100.0
reader = "simple"
category = "5th Grader"

[[source]]
name = "riddle_medium"
type = "gemini"
weight = 20.0
difficulty = "Medium"
points = 100

[[source]]
name = "jeopardy_easy"
type = "file"
dataset = "jeopardy"
weight = 25.0
reader = "jeopardy"
clue_values = [100, 200]
final_jeopardy_score_sub = 10000
points = 100
""")

    def tearDown(self):
        """Clean up temporary files."""
        import shutil

        shutil.rmtree(self.temp_dir)

    @patch("src.cfg.main.SOURCES_TOML_PATH")
    @patch("src.cfg.main.BASE_DIR")
    @patch("src.cfg.main.ConfigReader.validate_config")
    def test_load_toml_config_success(
        self, mock_validate, mock_base_dir, mock_toml_path
    ):
        """Test successful loading of TOML configuration."""
        mock_toml_path.__str__ = lambda _: self.sources_toml
        mock_toml_path.__fspath__ = lambda _: self.sources_toml
        mock_base_dir.__str__ = lambda _: self.temp_dir

        with patch("src.cfg.main.SOURCES_TOML_PATH", self.sources_toml):
            config = ConfigReader()
            toml_data = config._toml_config

            self.assertIn("datasets", toml_data)
            self.assertEqual(toml_data["datasets"]["jeopardy"], "datasets/jeopardy.tsv")
            self.assertIn("source", toml_data)
            self.assertEqual(
                len(toml_data["source"]), 3
            )  # 5th_grader, riddle_medium, jeopardy_easy

    @patch("src.cfg.main.SOURCES_TOML_PATH", "/nonexistent/sources.toml")
    @patch("src.cfg.main.ConfigReader.validate_config")
    def test_load_toml_config_missing_file(self, mock_validate):
        """Test that missing TOML file raises FileNotFoundError with clear message."""
        with self.assertRaises(FileNotFoundError) as context:
            ConfigReader()

        self.assertIn("Required configuration file not found", str(context.exception))

    @patch("src.cfg.main.SOURCES_TOML_PATH")
    @patch("src.cfg.main.ConfigReader.validate_config")
    def test_load_toml_config_malformed(self, mock_validate, mock_toml_path):
        """Test that malformed TOML raises ValueError with clear message."""
        malformed_toml = os.path.join(self.config_dir, "bad.toml")
        with open(malformed_toml, "w") as f:
            f.write("[datasets\n")  # Missing closing bracket

        mock_toml_path.__str__ = lambda _: malformed_toml
        mock_toml_path.__fspath__ = lambda _: malformed_toml

        with patch("src.cfg.main.SOURCES_TOML_PATH", malformed_toml):
            with self.assertRaises(ValueError) as context:
                ConfigReader()

            self.assertIn("Malformed TOML configuration", str(context.exception))

    @patch("src.cfg.main.SOURCES_TOML_PATH")
    @patch("src.cfg.main.BASE_DIR")
    @patch("src.cfg.main.ConfigReader.validate_config")
    def test_get_dataset_path_success(
        self, mock_validate, mock_base_dir, mock_toml_path
    ):
        """Test successful dataset path retrieval."""
        mock_toml_path.__str__ = lambda _: self.sources_toml
        mock_toml_path.__fspath__ = lambda _: self.sources_toml
        mock_base_dir.__str__ = lambda _: self.temp_dir

        with patch("src.cfg.main.SOURCES_TOML_PATH", self.sources_toml):
            with patch("src.cfg.main.BASE_DIR", self.temp_dir):
                config = ConfigReader()
                path = config.get_dataset_path("jeopardy")

                # Normalize paths for comparison (handles OS-specific separators)
                expected = os.path.normpath(
                    os.path.join(self.temp_dir, "datasets", "jeopardy.tsv")
                )
                actual = os.path.normpath(path)
                self.assertEqual(actual, expected)

    @patch("src.cfg.main.SOURCES_TOML_PATH")
    @patch("src.cfg.main.BASE_DIR")
    @patch("src.cfg.main.ConfigReader.validate_config")
    def test_get_dataset_path_missing_dataset(
        self, mock_validate, mock_base_dir, mock_toml_path
    ):
        """Test that missing dataset reference raises KeyError with helpful message."""
        mock_toml_path.__str__ = lambda _: self.sources_toml
        mock_toml_path.__fspath__ = lambda _: self.sources_toml

        with patch("src.cfg.main.SOURCES_TOML_PATH", self.sources_toml):
            config = ConfigReader()

            with self.assertRaises(KeyError) as context:
                config.get_dataset_path("nonexistent")

            self.assertIn("Dataset 'nonexistent' not found", str(context.exception))
            self.assertIn("Available datasets", str(context.exception))

    @patch("src.cfg.main.SOURCES_TOML_PATH")
    @patch("src.cfg.main.BASE_DIR")
    @patch("src.cfg.main.ConfigReader.validate_config")
    def test_parse_question_sources_gemini(
        self, mock_validate, mock_base_dir, mock_toml_path
    ):
        """Test parsing Gemini question sources from TOML."""
        mock_toml_path.__str__ = lambda _: self.sources_toml
        mock_toml_path.__fspath__ = lambda _: self.sources_toml

        mock_gemini = MagicMock()

        with patch("src.cfg.main.SOURCES_TOML_PATH", self.sources_toml):
            config = ConfigReader()
            sources = config.parse_question_sources(mock_gemini)

            # Should have 1 source (riddle_medium)
            # File sources will fail to load since we don't have actual files
            # But this is OK - they just get skipped with warnings
            gemini_sources = [s for s in sources if hasattr(s, "difficulty")]
            self.assertEqual(len(gemini_sources), 1)
            self.assertEqual(gemini_sources[0].name, "riddle_medium")
            self.assertEqual(gemini_sources[0].difficulty, "Medium")
            self.assertEqual(gemini_sources[0].default_points, 100)
            self.assertEqual(gemini_sources[0].weight, 20.0)

    @patch("src.cfg.main.SOURCES_TOML_PATH")
    @patch("src.cfg.main.BASE_DIR")
    @patch("src.cfg.main.ConfigReader.validate_config")
    def test_parse_question_sources_no_gemini_manager(
        self, mock_validate, mock_base_dir, mock_toml_path
    ):
        """Test that parse_question_sources raises error when no valid sources load."""
        mock_toml_path.__str__ = lambda _: self.sources_toml
        mock_toml_path.__fspath__ = lambda _: self.sources_toml

        with patch("src.cfg.main.SOURCES_TOML_PATH", self.sources_toml):
            config = ConfigReader()

            # No gemini_manager and no actual files means no sources will load
            # Should raise RuntimeError
            with self.assertRaises(RuntimeError) as context:
                config.parse_question_sources(None)

            self.assertIn(
                "Failed to load any valid question sources", str(context.exception)
            )

    @patch("src.cfg.main.SOURCES_TOML_PATH")
    @patch("src.cfg.main.BASE_DIR")
    @patch("src.cfg.main.ConfigReader.validate_config")
    def test_parse_question_sources_empty_config(
        self, mock_validate, mock_base_dir, mock_toml_path
    ):
        """Test that parse_question_sources raises error when no sources are defined."""
        # Create a TOML with no sources
        empty_toml = os.path.join(self.config_dir, "empty.toml")
        with open(empty_toml, "w") as f:
            f.write("""
[datasets]
jeopardy = "datasets/jeopardy.tsv"
""")

        mock_toml_path.__str__ = lambda _: empty_toml
        mock_toml_path.__fspath__ = lambda _: empty_toml

        with patch("src.cfg.main.SOURCES_TOML_PATH", empty_toml):
            config = ConfigReader()

            with self.assertRaises(RuntimeError) as context:
                config.parse_question_sources(None)

            self.assertIn("No question sources defined", str(context.exception))

    @patch("src.cfg.main.SOURCES_TOML_PATH")
    @patch("src.cfg.main.BASE_DIR")
    @patch("src.cfg.main.ConfigReader.validate_config")
    @patch("data.readers.csv_reader.read_simple_questions")
    def test_parse_question_sources_file_simple(
        self, mock_read_simple, mock_validate, mock_base_dir, mock_toml_path
    ):
        """Test parsing file-based source with simple reader."""
        # Create a TOML with a simple reader source
        toml_path = os.path.join(self.config_dir, "simple.toml")
        with open(toml_path, "w") as f:
            f.write("""
[datasets]
test_dataset = "datasets/test.csv"

[[source]]
name = "test_simple"
type = "file"
dataset = "test_dataset"
weight = 50.0
reader = "simple"
category = "Test Category"
points = 200
""")

        mock_toml_path.__str__ = lambda _: toml_path
        mock_toml_path.__fspath__ = lambda _: toml_path

        # Mock the reader to return questions
        from data.readers.question import Question

        mock_questions = [Question("Q1", "A1", "Test Category", 100)]
        mock_read_simple.return_value = mock_questions

        with patch("src.cfg.main.SOURCES_TOML_PATH", toml_path):
            with patch("src.cfg.main.BASE_DIR", self.temp_dir):
                config = ConfigReader()
                sources = config.parse_question_sources(None)

                self.assertEqual(len(sources), 1)
                self.assertEqual(sources[0].name, "test_simple")
                self.assertEqual(sources[0].weight, 50.0)
                self.assertEqual(sources[0].default_points, 200)

                # Verify the reader was called with correct args
                expected_path = os.path.normpath(
                    os.path.join(self.temp_dir, "datasets", "test.csv")
                )
                actual_call = mock_read_simple.call_args[0]
                self.assertEqual(os.path.normpath(actual_call[0]), expected_path)
                self.assertEqual(actual_call[1], "Test Category")

    @patch("src.cfg.main.SOURCES_TOML_PATH")
    @patch("src.cfg.main.BASE_DIR")
    @patch("src.cfg.main.ConfigReader.validate_config")
    @patch("data.readers.tsv.read_jeopardy_questions")
    def test_parse_question_sources_file_jeopardy_with_settings(
        self, mock_read_jeopardy, mock_validate, mock_base_dir, mock_toml_path
    ):
        """Test parsing Jeopardy source with difficulty-based settings."""
        toml_path = os.path.join(self.config_dir, "jeopardy.toml")
        with open(toml_path, "w") as f:
            f.write("""
[datasets]
jeopardy = "datasets/jeopardy.tsv"

[[source]]
name = "jeopardy_test"
type = "file"
dataset = "jeopardy"
weight = 75.0
reader = "jeopardy"
difficulty = "medium"
points = 150
""")

        mock_toml_path.__str__ = lambda _: toml_path
        mock_toml_path.__fspath__ = lambda _: toml_path

        from data.readers.question import Question

        mock_questions = [Question("Q1", "A1", "Jeopardy", 200)]
        mock_read_jeopardy.return_value = mock_questions

        with patch("src.cfg.main.SOURCES_TOML_PATH", toml_path):
            with patch("src.cfg.main.BASE_DIR", self.temp_dir):
                config = ConfigReader()
                sources = config.parse_question_sources(None)

                self.assertEqual(len(sources), 1)
                self.assertEqual(sources[0].name, "jeopardy_test")

                # Verify difficulty-based settings were passed
                expected_path = os.path.normpath(
                    os.path.join(self.temp_dir, "datasets", "jeopardy.tsv")
                )
                actual_call = mock_read_jeopardy.call_args
                self.assertEqual(os.path.normpath(actual_call[0][0]), expected_path)
                self.assertEqual(actual_call[1]["difficulty"], "medium")
                self.assertEqual(actual_call[1]["final_jeopardy_score"], 150)

    @patch("src.cfg.main.SOURCES_TOML_PATH")
    @patch("src.cfg.main.BASE_DIR")
    @patch("src.cfg.main.ConfigReader.validate_config")
    @patch("data.readers.csv_reader.read_knowledge_bowl_questions")
    @patch("data.readers.csv_reader.read_simple_questions")
    def test_parse_question_sources_multiple_file_sources(
        self, mock_simple, mock_kb, mock_validate, mock_base_dir, mock_toml_path
    ):
        """Test parsing multiple file sources with different reader types."""
        toml_path = os.path.join(self.config_dir, "multi.toml")
        with open(toml_path, "w") as f:
            f.write("""
[datasets]
kb = "datasets/kb.csv"
simple = "datasets/simple.csv"

[[source]]
name = "kb_source"
type = "file"
dataset = "kb"
weight = 60.0
reader = "knowledge_bowl"

[[source]]
name = "simple_source"
type = "file"
dataset = "simple"
weight = 40.0
reader = "simple"
category = "Simple"
""")

        mock_toml_path.__str__ = lambda _: toml_path
        mock_toml_path.__fspath__ = lambda _: toml_path

        from data.readers.question import Question

        mock_kb.return_value = [Question("KB1", "A1", "KB", 100)]
        mock_simple.return_value = [Question("S1", "A1", "Simple", 100)]

        with patch("src.cfg.main.SOURCES_TOML_PATH", toml_path):
            with patch("src.cfg.main.BASE_DIR", self.temp_dir):
                config = ConfigReader()
                sources = config.parse_question_sources(None)

                # Should have 2 file sources
                self.assertEqual(len(sources), 2)
                source_names = [s.name for s in sources]
                self.assertIn("kb_source", source_names)
                self.assertIn("simple_source", source_names)

                # Verify both readers were called
                self.assertTrue(mock_kb.called)
                self.assertTrue(mock_simple.called)

    @patch("src.cfg.main.SOURCES_TOML_PATH")
    @patch("src.cfg.main.BASE_DIR")
    @patch("src.cfg.main.ConfigReader.validate_config")
    def test_parse_question_sources_unknown_reader_type(
        self, mock_validate, mock_base_dir, mock_toml_path
    ):
        """Test that unknown reader types are logged and skipped."""
        toml_path = os.path.join(self.config_dir, "bad_reader.toml")
        with open(toml_path, "w") as f:
            f.write("""
[datasets]
test = "datasets/test.csv"

[[source]]
name = "bad_source"
type = "file"
dataset = "test"
weight = 50.0
reader = "nonexistent_reader"
""")

        mock_toml_path.__str__ = lambda _: toml_path
        mock_toml_path.__fspath__ = lambda _: toml_path

        with patch("src.cfg.main.SOURCES_TOML_PATH", toml_path):
            with patch("src.cfg.main.BASE_DIR", self.temp_dir):
                config = ConfigReader()

                # Should raise RuntimeError since no valid sources load
                with self.assertRaises(RuntimeError) as context:
                    config.parse_question_sources(None)

                self.assertIn(
                    "Failed to load any valid question sources", str(context.exception)
                )


if __name__ == "__main__":
    unittest.main()
