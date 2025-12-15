import unittest
from unittest.mock import MagicMock, patch
import os
from src.cfg.main import ConfigReader
from data.readers.question_source import GeminiQuestionSource


class TestConfigParsing(unittest.TestCase):
    def setUp(self):
        self.mock_gemini = MagicMock()
        # Patch os.environ to control config
        self.env_patcher = patch.dict(os.environ, {}, clear=True)
        self.env_patcher.start()
        self.config = ConfigReader()

    def tearDown(self):
        self.env_patcher.stop()

    def test_parse_question_sources_empty(self):
        # Ensure env var is empty, as ConfigReader might have loaded it from .env
        if "JBOT_EXTRA_SOURCES" in os.environ:
            del os.environ["JBOT_EXTRA_SOURCES"]
        sources = self.config.parse_question_sources(self.mock_gemini)
        self.assertEqual(sources, [])

    def test_parse_question_sources_gemini_valid(self):
        os.environ["JBOT_EXTRA_SOURCES"] = (
            "gemini:riddle_med:20:difficulty=Medium:points=200"
        )
        sources = self.config.parse_question_sources(self.mock_gemini)

        self.assertEqual(len(sources), 1)
        source = sources[0]
        self.assertIsInstance(source, GeminiQuestionSource)
        self.assertEqual(source.name, "riddle_med")
        self.assertEqual(source.weight, 20.0)
        self.assertEqual(source.difficulty, "Medium")
        self.assertEqual(source.default_points, 200)

    def test_parse_question_sources_multiple(self):
        os.environ["JBOT_EXTRA_SOURCES"] = "gemini:s1:10,gemini:s2:5:difficulty=Hard"
        sources = self.config.parse_question_sources(self.mock_gemini)

        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[0].name, "s1")
        self.assertEqual(sources[0].weight, 10.0)
        self.assertEqual(sources[1].name, "s2")
        self.assertEqual(sources[1].difficulty, "Hard")

    def test_parse_question_sources_invalid_format(self):
        os.environ["JBOT_EXTRA_SOURCES"] = "invalid_format,gemini:valid:10"
        sources = self.config.parse_question_sources(self.mock_gemini)

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].name, "valid")

    def test_parse_question_sources_invalid_weight(self):
        os.environ["JBOT_EXTRA_SOURCES"] = "gemini:bad_weight:abc"
        sources = self.config.parse_question_sources(self.mock_gemini)
        self.assertEqual(sources, [])

    def test_parse_question_sources_no_gemini_manager(self):
        os.environ["JBOT_EXTRA_SOURCES"] = "gemini:s1:10"
        sources = self.config.parse_question_sources(None)  # No manager
        self.assertEqual(sources, [])

    def test_parse_question_sources_invalid_points(self):
        os.environ["JBOT_EXTRA_SOURCES"] = "gemini:s1:10:points=abc"
        sources = self.config.parse_question_sources(self.mock_gemini)

        self.assertEqual(len(sources), 1)
        self.assertIsNone(sources[0].default_points)
