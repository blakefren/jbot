import unittest
from unittest.mock import patch, MagicMock
from src.core.gemini_manager import GeminiManager


class TestGeminiManager(unittest.TestCase):
    @patch("src.core.gemini_manager.genai")
    def setUp(self, mock_genai):
        self.mock_genai = mock_genai
        self.gemini_manager = GeminiManager(api_key="test_key")
        self.model_mock = self.mock_genai.GenerativeModel.return_value

    def test_init_success(self):
        self.mock_genai.configure.assert_called_once_with(api_key="test_key")
        self.mock_genai.GenerativeModel.assert_called_once_with("gemini-2.5-pro")
        self.assertIsNotNone(self.gemini_manager.model)

    def test_init_no_api_key(self):
        with self.assertRaises(ValueError):
            GeminiManager(api_key="")

    def test_generate_content_success(self):
        mock_response = MagicMock()
        mock_response.text = "Hello there!"
        self.model_mock.generate_content.return_value = mock_response

        response = self.gemini_manager.generate_content("Hello")
        self.assertEqual(response, "Hello there!")
        self.model_mock.generate_content.assert_called_once_with(
            "Hello", generation_config=None
        )

    def test_generate_content_failure(self):
        self.model_mock.generate_content.side_effect = Exception("API Error")

        response = self.gemini_manager.generate_content("Hello")
        self.assertIsNone(response)


if __name__ == "__main__":
    unittest.main()
