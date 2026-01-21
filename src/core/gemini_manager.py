"""
Manager for interacting with the Gemini API using the google-generativeai library.
"""

import google.generativeai as genai
import logging


class GeminiManager:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Gemini API key is required.")
        try:
            self.api_key = api_key
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel("gemini-2.5-pro")
            logging.info("GeminiManager initialized successfully.")
        except Exception as e:
            logging.error(f"Failed to configure Gemini: {e}")
            raise

    def generate_content(self, text: str, generation_config: dict = None) -> str:
        """
        Generates content using the Gemini API.

        Args:
            text: The prompt text.
            generation_config: Optional configuration for generation (e.g., temperature).
        """
        try:
            response = self.model.generate_content(
                text, generation_config=generation_config
            )
            return response.text
        except Exception as e:
            logging.error(f"An error occurred during Gemini content generation: {e}")
            return None
