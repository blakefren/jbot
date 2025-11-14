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
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel("gemini-2.5-pro")
            logging.info("GeminiManager initialized successfully.")
        except Exception as e:
            logging.error(f"Failed to configure Gemini: {e}")
            raise

    def generate_content(self, text: str) -> str:
        """
        Generates content using the Gemini API.
        """
        try:
            response = self.model.generate_content(text)
            return response.text
        except Exception as e:
            logging.error(f"An error occurred during Gemini content generation: {e}")
            return None
