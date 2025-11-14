import unittest
from unittest.mock import patch, MagicMock
import requests
from src.core.api_manager import APIManager


class TestAPIManager(unittest.TestCase):
    def setUp(self):
        self.api_manager = APIManager(api_key="test_key", base_url="http://fakeapi.com")

    @patch("requests.get")
    def test_get_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"data": "success"}
        mock_get.return_value = mock_response

        response = self.api_manager.get("test_endpoint")
        self.assertEqual(response, {"data": "success"})
        mock_get.assert_called_once_with(
            "http://fakeapi.com/test_endpoint",
            headers=self.api_manager.headers,
            params=None,
        )

    @patch("requests.get")
    def test_get_failure(self, mock_get):
        mock_get.side_effect = requests.exceptions.RequestException("API error")

        response = self.api_manager.get("test_endpoint")
        self.assertIsNone(response)

    @patch("requests.post")
    def test_post_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"data": "created"}
        mock_post.return_value = mock_response

        post_data = {"key": "value"}
        response = self.api_manager.post("test_endpoint", data=post_data)
        self.assertEqual(response, {"data": "created"})
        mock_post.assert_called_once_with(
            "http://fakeapi.com/test_endpoint",
            headers=self.api_manager.headers,
            json=post_data,
        )

    @patch("requests.post")
    def test_post_failure(self, mock_post):
        mock_post.side_effect = requests.exceptions.RequestException("API error")

        response = self.api_manager.post("test_endpoint", data={})
        self.assertIsNone(response)


if __name__ == "__main__":
    unittest.main()
