"""
Manager for interacting with the Gemini API using the google-genai library.
"""

import time

from google import genai
from google.genai import types
import logging

# Seconds to wait between retries (one value per gap between attempts)
_RETRY_DELAYS = (5, 10)


class GeminiManager:
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-pro",
        fallback_model: str = None,
    ):
        if not api_key:
            raise ValueError("Gemini API key is required.")
        try:
            self.api_key = api_key
            self.model = model
            self.fallback_model = fallback_model
            self.client = genai.Client(api_key=self.api_key)
            logging.info("GeminiManager initialized successfully.")
        except Exception as e:
            logging.error(f"Failed to configure Gemini: {e}")
            raise

    def generate_content(self, text: str, generation_config: dict = None) -> str:
        """
        Generates content using the Gemini API.

        Retries up to len(_RETRY_DELAYS)+1 times on the primary model before
        falling back to fallback_model (if configured). Returns None if all
        attempts fail.

        Note: This is a blocking call. Callers from async Discord tasks should
        wrap this via asyncio.to_thread() to prevent blocking the event loop.

        Args:
            text: The prompt text.
            generation_config: Optional configuration for generation (e.g., temperature).
        """
        # Convert generation_config dict to GenerateContentConfig if provided
        config = None
        if generation_config:
            config = types.GenerateContentConfig(**generation_config)

        max_attempts = len(_RETRY_DELAYS) + 1
        last_error = None

        # Try primary model with retries
        for attempt in range(max_attempts):
            try:
                response = self.client.models.generate_content(
                    model=self.model, contents=text, config=config
                )
                return response.text
            except Exception as e:
                last_error = e
                if attempt < len(_RETRY_DELAYS):
                    delay = _RETRY_DELAYS[attempt]
                    logging.warning(
                        f"Gemini content generation attempt {attempt + 1}/{max_attempts} "
                        f"failed (model={self.model}): {e}. Retrying in {delay}s..."
                    )
                    time.sleep(delay)
                else:
                    logging.warning(
                        f"Primary model {self.model} failed after {max_attempts} attempts: {e}"
                    )

        # Try fallback model if configured
        if self.fallback_model:
            logging.info(
                f"Attempting fallback model: {self.fallback_model}"
            )
            try:
                response = self.client.models.generate_content(
                    model=self.fallback_model, contents=text, config=config
                )
                return response.text
            except Exception as e:
                last_error = e
                logging.warning(
                    f"Fallback model {self.fallback_model} also failed: {e}"
                )

        logging.error(f"An error occurred during Gemini content generation: {last_error}")
        return None
