"""
Manager for interacting with the Gemini API.
"""
from src.core.api_manager import APIManager


class GeminiManager(APIManager):
    def __init__(self, api_key: str):
        super().__init__(
            api_key, base_url="https://generativelanguage.googleapis.com/v1beta"
        )

    def generate_content(self, text: str) -> dict:
        """
        Generates content using the Gemini API.
        """
        endpoint = "models/gemini-pro:generateContent"
        data = {"contents": [{"parts": [{"text": text}]}]}
        return self.post(endpoint, data)
