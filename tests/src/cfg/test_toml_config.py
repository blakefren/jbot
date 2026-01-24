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
            f.write(
                """
[datasets]
jeopardy = "datasets/jeopardy.tsv"
knowledge_bowl = "datasets/kb.csv"

[[source]]
name = "default"
type = "default"
weight = 100.0

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
clue_values = [100, 200]
points = 100
"""
            )

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
            self.assertEqual(len(toml_data["source"]), 3)

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
    @patch.dict(os.environ, {"JBOT_FINAL_JEOPARDY_SCORE_SUB": "10000"})
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

            # Should have 2 sources (default is skipped, riddle_medium + jeopardy_easy)
            # But jeopardy_easy will fail to load since we don't have actual file
            # So we'll only get riddle_medium
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
        """Test that Gemini sources are skipped when no manager is provided."""
        mock_toml_path.__str__ = lambda _: self.sources_toml
        mock_toml_path.__fspath__ = lambda _: self.sources_toml

        with patch("src.cfg.main.SOURCES_TOML_PATH", self.sources_toml):
            config = ConfigReader()
            sources = config.parse_question_sources(None)  # No gemini_manager

            # Should have 0 Gemini sources
            gemini_sources = [s for s in sources if hasattr(s, "difficulty")]
            self.assertEqual(len(gemini_sources), 0)


if __name__ == "__main__":
    unittest.main()
