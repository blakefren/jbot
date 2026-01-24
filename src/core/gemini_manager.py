"""
Manager for interacting with the Gemini API using the google-genai library.
"""

from google import genai
from google.genai import types
import logging


class GeminiManager:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Gemini API key is required.")
        try:
            self.api_key = api_key
            self.client = genai.Client(api_key=self.api_key)
            logging.info("GeminiManager initialized successfully.")
        except Exception as e:
            logging.error(f"Failed to configure Gemini: {e}")
            raise

    def generate_content(self, text: str, generation_config: dict = None) -> str:
        """
        Generates content using the Gemini API.

        Note: This is a blocking call that can take 10+ seconds. In the future,
        consider making this async using asyncio.to_thread() to prevent blocking
        Discord's event loop during API calls.

        Args:
            text: The prompt text.
            generation_config: Optional configuration for generation (e.g., temperature).
        """
        try:
            # Convert generation_config dict to GenerateContentConfig if provided
            config = None
            if generation_config:
                config = types.GenerateContentConfig(**generation_config)

            response = self.client.models.generate_content(
                model="gemini-2.5-pro", contents=text, config=config
            )
            return response.text
        except Exception as e:
            logging.error(f"An error occurred during Gemini content generation: {e}")
            return None
