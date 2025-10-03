import unittest
from unittest.mock import patch, mock_open
from cfg.main import ConfigReader


class TestConfigReader(unittest.TestCase):

    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="key1: value1\nkey2: value2\n#comment\nkey3:true",
    )
    @patch("cfg.main.CONFIG_FILE_PATH", "dummy/path/main.cfg")
    def test_init_success(self, mock_open_file):
        """Test successful initialization and reading of a config file."""
        config_reader = ConfigReader()
        self.assertEqual(config_reader.get("key1"), "value1")
        self.assertEqual(config_reader.get("key2"), "value2")
        self.assertTrue(config_reader.get_bool("key3"))
        self.assertIsNone(config_reader.get("non_existent_key"))

    @patch("builtins.open", side_effect=FileNotFoundError)
    @patch("cfg.main.CONFIG_FILE_PATH", "dummy/path/main.cfg")
    def test_init_file_not_found(self, mock_open_file):
        """Test FileNotFoundError during initialization."""
        config_reader = ConfigReader()
        self.assertEqual(config_reader.config, {})

    @patch("builtins.open", side_effect=Exception("Test error"))
    @patch("cfg.main.CONFIG_FILE_PATH", "dummy/path/main.cfg")
    def test_init_exception(self, mock_open_file):
        """Test a generic exception during file reading."""
        config_reader = ConfigReader()
        self.assertEqual(config_reader.config, {})

    def test_get_existing_key(self):
        """Test getting an existing key."""
        config_reader = ConfigReader()
        config_reader.config = {"key1": "value1"}
        self.assertEqual(config_reader.get("key1"), "value1")

    def test_get_non_existing_key(self):
        """Test getting a non-existing key returns None."""
        config_reader = ConfigReader()
        config_reader.config = {"key1": "value1"}
        self.assertIsNone(config_reader.get("non_existent_key"))

    def test_get_non_existing_key_with_default(self):
        """Test getting a non-existing key with a default value."""
        config_reader = ConfigReader()
        config_reader.config = {"key1": "value1"}
        self.assertEqual(
            config_reader.get("non_existent_key", "default_val"), "default_val"
        )

    def test_get_bool_true(self):
        """Test getting various 'true' boolean values."""
        config_reader = ConfigReader()
        config_reader.config = {
            "true_val": "true",
            "one_val": "1",
            "t_val": "t",
            "y_val": "y",
            "yes_val": "yes",
            "mixed_case": "True",
        }
        self.assertTrue(config_reader.get_bool("true_val"))
        self.assertTrue(config_reader.get_bool("one_val"))
        self.assertTrue(config_reader.get_bool("t_val"))
        self.assertTrue(config_reader.get_bool("y_val"))
        self.assertTrue(config_reader.get_bool("yes_val"))
        self.assertTrue(config_reader.get_bool("mixed_case"))

    def test_get_bool_false(self):
        """Test getting 'false' boolean values."""
        config_reader = ConfigReader()
        config_reader.config = {"false_val": "false", "other_val": "any other value"}
        self.assertFalse(config_reader.get_bool("false_val"))
        self.assertFalse(config_reader.get_bool("other_val"))

    def test_get_bool_non_existing(self):
        """Test getting a boolean for a non-existing key."""
        config_reader = ConfigReader()
        config_reader.config = {}
        with self.assertRaises(KeyError):
            config_reader.get_bool("non_existent_key")


if __name__ == "__main__":
    unittest.main()
