import unittest
from unittest.mock import patch, MagicMock
from src.core.gemini_manager import GeminiManager


class TestGeminiManager(unittest.TestCase):
    def setUp(self):
        self.gemini_manager = GeminiManager(api_key="test_key")

    @patch("src.core.api_manager.APIManager.post")
    def test_generate_content_success(self, mock_post):
        mock_post.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Hello there!"}]}}]
        }

        response = self.gemini_manager.generate_content("Hello")
        self.assertEqual(
            response,
            {"candidates": [{"content": {"parts": [{"text": "Hello there!"}]}}]},
        )

        expected_data = {"contents": [{"parts": [{"text": "Hello"}]}]}
        mock_post.assert_called_once_with(
            "models/gemini-pro:generateContent", expected_data
        )

    @patch("src.core.api_manager.APIManager.post")
    def test_generate_content_failure(self, mock_post):
        mock_post.return_value = None

        response = self.gemini_manager.generate_content("Hello")
        self.assertIsNone(response)


if __name__ == "__main__":
    unittest.main()
