import unittest
import os
from unittest.mock import patch, mock_open, MagicMock
from src.cfg.main import ConfigReader, load_config, MissingConfigurationError


class TestConfigReader(unittest.TestCase):
    @patch("src.cfg.main.load_dotenv")
    @patch("shutil.copy")
    @patch("os.path.exists")
    def test_load_config_creates_env_if_not_exists(
        self, mock_exists, mock_copy, mock_load_dotenv
    ):
        """Test that .env file is created from template if it doesn't exist."""
        mock_exists.return_value = False
        load_config()
        mock_copy.assert_called_once()
        mock_load_dotenv.assert_called_once()

    @patch("src.cfg.main.load_dotenv")
    @patch("shutil.copy")
    @patch("os.path.exists")
    def test_load_config_does_not_create_env_if_exists(
        self, mock_exists, mock_copy, mock_load_dotenv
    ):
        """Test that .env file is not created if it already exists."""
        mock_exists.return_value = True
        load_config()
        mock_copy.assert_not_called()
        mock_load_dotenv.assert_called_once()

    @patch("src.cfg.main.ConfigReader.validate_config")
    @patch.dict(os.environ, {"JBOT_KEY1": "value1"})
    def test_get_existing_key(self, mock_validate):
        """Test getting an existing key."""
        config_reader = ConfigReader()
        self.assertEqual(config_reader.get("JBOT_KEY1"), "value1")

    @patch("src.cfg.main.ConfigReader.validate_config")
    def test_get_non_existing_key(self, mock_validate):
        """Test getting a non-existing key raises MissingConfigurationError."""
        config_reader = ConfigReader()
        with self.assertRaises(MissingConfigurationError):
            config_reader.get("JBOT_NON_EXISTENT_KEY")

    @patch("src.cfg.main.ConfigReader.validate_config")
    def test_get_non_existing_key_with_default(self, mock_validate):
        """Test getting a non-existing key with a default value."""
        config_reader = ConfigReader()
        self.assertEqual(
            config_reader.get("JBOT_NON_EXISTENT_KEY", "default_val"), "default_val"
        )

    @patch.dict(
        os.environ,
        {
            "JBOT_TRUE_VAL": "true",
            "JBOT_ONE_VAL": "1",
            "JBOT_T_VAL": "t",
            "JBOT_Y_VAL": "y",
            "JBOT_YES_VAL": "yes",
            "JBOT_MIXED_CASE": "True",
        },
    )
    def test_get_bool_true(self):
        """Test getting various 'true' boolean values."""
        config_reader = ConfigReader()
        self.assertTrue(config_reader.get_bool("JBOT_TRUE_VAL"))
        self.assertTrue(config_reader.get_bool("JBOT_ONE_VAL"))
        self.assertTrue(config_reader.get_bool("JBOT_T_VAL"))
        self.assertTrue(config_reader.get_bool("JBOT_Y_VAL"))
        self.assertTrue(config_reader.get_bool("JBOT_YES_VAL"))
        self.assertTrue(config_reader.get_bool("JBOT_MIXED_CASE"))

    @patch.dict(
        os.environ,
        {"JBOT_FALSE_VAL": "false", "JBOT_OTHER_VAL": "any other value"},
    )
    def test_get_bool_false(self):
        """Test getting 'false' boolean values."""
        config_reader = ConfigReader()
        self.assertFalse(config_reader.get_bool("JBOT_FALSE_VAL"))
        self.assertFalse(config_reader.get_bool("JBOT_OTHER_VAL"))

    def test_get_bool_non_existing(self):
        """Test getting a boolean for a non-existing key."""
        config_reader = ConfigReader()
        with self.assertRaises(MissingConfigurationError):
            config_reader.get_bool("JBOT_NON_EXISTENT_KEY")

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test_api_key_12345"})
    def test_get_gemini_api_key_success(self):
        """Test successfully retrieving the Gemini API key."""
        config_reader = ConfigReader()
        self.assertEqual(config_reader.get_gemini_api_key(), "test_api_key_12345")

    def test_get_gemini_api_key_not_found(self):
        """Test that MissingConfigurationError is raised when GEMINI_API_KEY is not set."""
        config_reader = ConfigReader()
        # Ensure the key is not in the environment
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MissingConfigurationError) as context:
                config_reader.get_gemini_api_key()
            self.assertIn("GEMINI_API_KEY", str(context.exception))

    def test_parse_question_sources_empty(self):
        config_reader = ConfigReader()
        with patch.dict(os.environ, {}, clear=True):
            sources = config_reader.parse_question_sources()
            self.assertEqual(sources, [])

    def test_parse_question_sources_gemini(self):
        config_reader = ConfigReader()
        mock_gemini = MagicMock()

        env = {
            "JBOT_EXTRA_SOURCES": "gemini:riddle_med:20:difficulty=Medium:points=200,gemini:riddle_hard:10:difficulty=Hard"
        }

        with patch.dict(os.environ, env, clear=True):
            sources = config_reader.parse_question_sources(gemini_manager=mock_gemini)

            self.assertEqual(len(sources), 2)

            s1 = sources[0]
            self.assertEqual(s1.name, "riddle_med")
            self.assertEqual(s1.weight, 20.0)
            self.assertEqual(s1.difficulty, "Medium")
            self.assertEqual(s1.default_points, 200)

            s2 = sources[1]
            self.assertEqual(s2.name, "riddle_hard")
            self.assertEqual(s2.weight, 10.0)
            self.assertEqual(s2.difficulty, "Hard")
            self.assertIsNone(s2.default_points)

    def test_parse_question_sources_gemini_no_manager(self):
        config_reader = ConfigReader()
        env = {"JBOT_EXTRA_SOURCES": "gemini:riddle:20"}
        with patch.dict(os.environ, env, clear=True):
            sources = config_reader.parse_question_sources(gemini_manager=None)
            self.assertEqual(sources, [])

    def test_parse_question_sources_invalid_format(self):
        config_reader = ConfigReader()
        env = {"JBOT_EXTRA_SOURCES": "invalid_format,gemini:ok:10"}
        mock_gemini = MagicMock()
        with patch.dict(os.environ, env, clear=True):
            sources = config_reader.parse_question_sources(gemini_manager=mock_gemini)
            self.assertEqual(len(sources), 1)
            self.assertEqual(sources[0].name, "ok")

    def test_parse_question_sources_invalid_weight(self):
        config_reader = ConfigReader()
        env = {"JBOT_EXTRA_SOURCES": "gemini:bad_weight:abc"}
        mock_gemini = MagicMock()
        with patch.dict(os.environ, env, clear=True):
            sources = config_reader.parse_question_sources(gemini_manager=mock_gemini)
            self.assertEqual(sources, [])

    @patch.dict(os.environ, {"GEMINI_API_KEY": ""})
    def test_get_gemini_api_key_empty(self):
        """Test that ValueError is raised when GEMINI_API_KEY is empty."""
        config_reader = ConfigReader()
        with self.assertRaises(ValueError) as context:
            config_reader.get_gemini_api_key()
        self.assertIn("GEMINI_API_KEY not found", str(context.exception))

    @patch("data.readers.tsv.read_jeopardy_questions")
    def test_parse_question_sources_file_jeopardy(self, mock_read_jeopardy):
        config_reader = ConfigReader()

        # Mock the questions returned
        mock_read_jeopardy.return_value = ["q1", "q2"]

        env = {
            "JBOT_EXTRA_SOURCES": "file:jeopardy:25:clue_values=100|200:points=50",
            "JBOT_JEOPARDY_LOCAL_PATH": "dummy_path.tsv",
            "JBOT_FINAL_JEOPARDY_SCORE_SUB": "500",
        }

        with patch.dict(os.environ, env, clear=True):
            sources = config_reader.parse_question_sources()

            self.assertEqual(len(sources), 1)
            source = sources[0]
            self.assertEqual(source.name, "jeopardy")
            self.assertEqual(source.weight, 25.0)
            self.assertEqual(source.default_points, 50)

            # Verify read_jeopardy_questions was called with correct args
            args, kwargs = mock_read_jeopardy.call_args
            self.assertEqual(kwargs["allowed_clue_values"], [100, 200])


if __name__ == "__main__":
    unittest.main()
