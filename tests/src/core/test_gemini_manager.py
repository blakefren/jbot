import unittest
from unittest.mock import patch, MagicMock
from src.core.gemini_manager import GeminiManager


class TestGeminiManager(unittest.TestCase):
    @patch("src.core.gemini_manager.genai.Client")
    def setUp(self, mock_client_class):
        self.mock_client_class = mock_client_class
        self.mock_client = MagicMock()
        self.mock_client_class.return_value = self.mock_client
        self.gemini_manager = GeminiManager(api_key="test_key", model="gemini-test")

    def test_init_success(self):
        self.mock_client_class.assert_called_once_with(api_key="test_key")
        self.assertIsNotNone(self.gemini_manager.client)

    def test_init_no_api_key(self):
        with self.assertRaises(ValueError):
            GeminiManager(api_key="")

    def test_generate_content_success(self):
        mock_response = MagicMock()
        mock_response.text = "Hello there!"
        self.mock_client.models.generate_content.return_value = mock_response

        response = self.gemini_manager.generate_content("Hello")
        self.assertEqual(response, "Hello there!")
        self.mock_client.models.generate_content.assert_called_once_with(
            model="gemini-test", contents="Hello", config=None
        )

    def test_generate_content_failure(self):
        self.mock_client.models.generate_content.side_effect = Exception("API Error")

        response = self.gemini_manager.generate_content("Hello")
        self.assertIsNone(response)


if __name__ == "__main__":
    unittest.main()
