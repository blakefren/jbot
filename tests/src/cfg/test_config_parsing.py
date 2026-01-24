import unittest
from unittest.mock import MagicMock, patch
import os
from src.cfg.main import ConfigReader


class TestConfigParsing(unittest.TestCase):
    """
    Tests for configuration parsing.
    Note: JBOT_EXTRA_SOURCES parsing has been deprecated in favor of TOML configuration.
    See test_toml_config.py for new TOML-based tests.
    """

    def setUp(self):
        self.mock_gemini = MagicMock()
        # Patch os.environ to control config
        self.env_patcher = patch.dict(os.environ, {}, clear=True)
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()


if __name__ == "__main__":
    unittest.main()
