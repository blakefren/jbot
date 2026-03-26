import unittest
import logging
import os
import sys
from logging import handlers

# Add the project root to the Python path
project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
sys.path.insert(0, project_root)

from src.logging_config import setup_logging


class TestLoggingConfig(unittest.TestCase):
    def setUp(self):
        """Set up for test cases."""
        # Use a temporary file for logging during tests
        self.test_log_file = "test_jbot.log"
        # Ensure the test log file doesn't exist before a test
        if os.path.exists(self.test_log_file):
            os.remove(self.test_log_file)

    def tearDown(self):
        """Clean up after test cases."""
        # Clean up the log file created during the test
        logging.shutdown()
        if os.path.exists(self.test_log_file):
            os.remove(self.test_log_file)

    def test_setup_logging_creates_file_handler_with_utf8(self):
        """
        Tests that setup_logging configures a file handler with UTF-8 encoding.
        """
        setup_logging(log_file_path=self.test_log_file)

        file_handler_found = False
        # Handlers are attached to the root logger so all logging.info() calls are captured.
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                file_handler_found = True
                self.assertEqual(
                    handler.encoding, "utf-8", "File handler encoding is not 'utf-8'"
                )

        self.assertTrue(
            file_handler_found,
            "No RotatingFileHandler found in root logger's handlers.",
        )

    def test_logging_with_emoji(self):
        """
        Tests that logging a message with an emoji does not raise an error and is written correctly.
        """
        setup_logging(log_file_path=self.test_log_file)

        test_message = "This is a test with an emoji: 😐"

        logger = logging.getLogger("jbot")
        try:
            logger.info(test_message)
        except UnicodeEncodeError:
            self.fail("Logging with an emoji raised a UnicodeEncodeError.")

        # We need to shut down logging to ensure the file handle is released
        logging.shutdown()

        # Ensure the log file was created
        self.assertTrue(os.path.exists(self.test_log_file), "Log file was not created.")

        # Verify the content of the log file
        with open(self.test_log_file, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn(
                test_message,
                content,
                "The emoji message was not found in the log file.",
            )


if __name__ == "__main__":
    unittest.main()
