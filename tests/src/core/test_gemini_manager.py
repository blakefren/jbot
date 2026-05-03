import unittest
from unittest.mock import patch, MagicMock, call
from src.core.gemini_manager import GeminiManager, _RETRY_DELAYS


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

    def test_init_fallback_model(self):
        with patch("src.core.gemini_manager.genai.Client"):
            mgr = GeminiManager(
                api_key="key", model="gemini-primary", fallback_model="gemini-fallback"
            )
        self.assertEqual(mgr.fallback_model, "gemini-fallback")

    def test_generate_content_success(self):
        mock_response = MagicMock()
        mock_response.text = "Hello there!"
        self.mock_client.models.generate_content.return_value = mock_response

        response = self.gemini_manager.generate_content("Hello")
        self.assertEqual(response, "Hello there!")
        self.mock_client.models.generate_content.assert_called_once_with(
            model="gemini-test", contents="Hello", config=None
        )

    @patch("src.core.gemini_manager.time.sleep")
    def test_generate_content_retries_then_succeeds(self, mock_sleep):
        """Verify that a transient failure is retried and succeeds on second attempt."""
        mock_response = MagicMock()
        mock_response.text = "Success on retry"
        self.mock_client.models.generate_content.side_effect = [
            Exception("503 UNAVAILABLE"),
            mock_response,
        ]

        response = self.gemini_manager.generate_content("Hello")

        self.assertEqual(response, "Success on retry")
        self.assertEqual(self.mock_client.models.generate_content.call_count, 2)
        mock_sleep.assert_called_once_with(_RETRY_DELAYS[0])

    @patch("src.core.gemini_manager.time.sleep")
    def test_generate_content_exhausts_retries_returns_none(self, mock_sleep):
        """Verify that exhausting all retries with no fallback returns None."""
        max_attempts = len(_RETRY_DELAYS) + 1
        self.mock_client.models.generate_content.side_effect = Exception(
            "503 UNAVAILABLE"
        )

        response = self.gemini_manager.generate_content("Hello")

        self.assertIsNone(response)
        self.assertEqual(
            self.mock_client.models.generate_content.call_count, max_attempts
        )
        self.assertEqual(mock_sleep.call_count, len(_RETRY_DELAYS))

    @patch("src.core.gemini_manager.time.sleep")
    def test_generate_content_falls_back_to_fallback_model(self, mock_sleep):
        """Verify that after primary model fails, the fallback model is tried."""
        with patch("src.core.gemini_manager.genai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mgr = GeminiManager(
                api_key="key", model="gemini-primary", fallback_model="gemini-fallback"
            )

        mock_fallback_response = MagicMock()
        mock_fallback_response.text = "Fallback result"

        max_attempts = len(_RETRY_DELAYS) + 1

        def side_effect(model, contents, config):
            if model == "gemini-primary":
                raise Exception("503 UNAVAILABLE")
            return mock_fallback_response

        mock_client.models.generate_content.side_effect = side_effect

        response = mgr.generate_content("Hello")

        self.assertEqual(response, "Fallback result")
        # Primary tried max_attempts times, fallback tried once
        self.assertEqual(
            mock_client.models.generate_content.call_count, max_attempts + 1
        )

    @patch("src.core.gemini_manager.time.sleep")
    def test_generate_content_fallback_also_fails_returns_none(self, mock_sleep):
        """Verify None is returned when both primary and fallback models fail."""
        with patch("src.core.gemini_manager.genai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mgr = GeminiManager(
                api_key="key", model="gemini-primary", fallback_model="gemini-fallback"
            )

        mock_client.models.generate_content.side_effect = Exception("503 UNAVAILABLE")

        response = mgr.generate_content("Hello")

        self.assertIsNone(response)

    def test_generate_content_failure(self):
        self.mock_client.models.generate_content.side_effect = Exception("API Error")

        response = self.gemini_manager.generate_content("Hello")
        self.assertIsNone(response)


if __name__ == "__main__":
    unittest.main()
