import os
import shutil
from dotenv import load_dotenv
import logging

# Define the paths for the .env files
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
ENV_PATH = os.path.join(BASE_DIR, ".env")
ENV_TEMPLATE_PATH = os.path.join(BASE_DIR, ".env.template")


def load_config():
    """
    Load the .env file. If it doesn't exist, create it from the template.
    """
    if not os.path.exists(ENV_PATH):
        logging.info(f"Creating .env file from template: {ENV_TEMPLATE_PATH}")
        shutil.copy(ENV_TEMPLATE_PATH, ENV_PATH)
    load_dotenv(dotenv_path=ENV_PATH)


class MissingConfigurationError(Exception):
    """Raised when a required configuration key is missing."""

    pass


class ConfigReader:
    """
    A class to read configuration from environment variables.
    """

    def __init__(self):
        """
        Loads configuration from environment variables.
        """
        load_config()
        self.validate_config()

    def validate_config(self):
        """
        Validates that all keys in .env.template exist in the current configuration.
        """
        if not os.path.exists(ENV_TEMPLATE_PATH):
            logging.warning(
                f"Template file not found at {ENV_TEMPLATE_PATH}, skipping validation."
            )
            return

        missing_keys = []
        with open(ENV_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # key=value
                if "=" in line:
                    key = line.split("=", 1)[0].strip()
                    if key not in os.environ:
                        missing_keys.append(key)

        if missing_keys:
            raise MissingConfigurationError(
                f"Missing {len(missing_keys)} critical configuration keys: {', '.join(missing_keys)}\n"
                f"Please update your .env file specific values match those in .env.template."
            )

    def get(self, key: str, default=None):
        """
        Retrieves a configuration value by key from environment variables.

        Args:
            key (str): The key to look for in the environment variables.
            default: The default value to return if the key is not found.
                     DEPRECATED: Supply defaults in .env.template instead.

        Returns:
            The value associated with the key.

        Raises:
            MissingConfigurationError: If the key is not found and no default is provided.
        """
        value = os.environ.get(key)

        if value is None:
            if default is not None:
                return default
            raise MissingConfigurationError(
                f"Configuration key '{key}' is missing from environment."
            )

        return value

    def get_bool(self, key: str) -> bool:
        """
        Retrieves a boolean configuration value by key.

        Args:
            key (str): The key to look for in the configuration.

        Returns:
            bool: The boolean value associated with the key.
        """
        value = self.get(key)
        return value.lower() in ("true", "1", "t", "y", "yes")

    def get_gemini_api_key(self) -> str:
        """
        Retrieves the Gemini API key from environment variables.

        Returns:
            str: The Gemini API key.
        """
        key = self.get("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY not found in environment variables.")
        return key

    def parse_question_sources(self, gemini_manager=None):
        """
        Parses the JBOT_EXTRA_SOURCES configuration and returns a list of QuestionSource objects.
        """
        from data.readers.question_source import (
            GeminiQuestionSource,
            StaticQuestionSource,
        )
        from data.readers.tsv import read_jeopardy_questions

        try:
            sources_config = self.get("JBOT_EXTRA_SOURCES")
        except MissingConfigurationError:
            return []

        sources = []

        if not sources_config:
            return sources

        for s_str in sources_config.split(","):
            parts = s_str.split(":")

            if len(parts) < 3:
                logging.warning(f"Invalid source config format: {s_str}")
                continue

            s_type = parts[0].strip()
            s_name = parts[1].strip()

            try:
                s_weight = float(parts[2].strip())
            except ValueError:
                logging.error(f"Invalid weight for source {s_name}: {parts[2]}")
                continue

            # Parse args
            args = {}
            if len(parts) > 3:
                for arg in parts[3:]:
                    if "=" in arg:
                        k, v = arg.split("=", 1)
                        args[k.strip()] = v.strip()

            # Extract common args
            default_points = args.get("points")
            if default_points:
                try:
                    default_points = int(default_points)
                except ValueError:
                    logging.warning(
                        f"Invalid points value for source {s_name}: {default_points}"
                    )
                    default_points = None

            if s_type == "gemini":
                if not gemini_manager:
                    logging.warning(
                        f"Skipping Gemini source {s_name} because GeminiManager is not available."
                    )
                    continue

                difficulty = args.get("difficulty", "Medium")
                sources.append(
                    GeminiQuestionSource(
                        s_name, s_weight, gemini_manager, difficulty, default_points
                    )
                )
                logging.info(
                    f"Added Gemini source: {s_name} (weight={s_weight}, difficulty={difficulty}, points={default_points})"
                )

            elif s_type == "file":
                questions = []
                if s_name == "jeopardy":
                    path = os.path.join(BASE_DIR, self.get("JBOT_JEOPARDY_LOCAL_PATH"))
                    score_sub = self.get("JBOT_FINAL_JEOPARDY_SCORE_SUB")

                    # Parse allowed clue values from args, default to [100] as requested
                    allowed_values = [100]
                    if "clue_values" in args:
                        try:
                            allowed_values = [
                                int(v) for v in args["clue_values"].split("|")
                            ]
                        except ValueError:
                            logging.warning(
                                f"Invalid clue_values for source {s_name}: {args['clue_values']}"
                            )

                    questions = read_jeopardy_questions(
                        path, score_sub, allowed_clue_values=allowed_values
                    )

                if questions:
                    sources.append(
                        StaticQuestionSource(
                            s_name, s_weight, questions, default_points
                        )
                    )
                    logging.info(
                        f"Added file source: {s_name} (weight={s_weight}, questions={len(questions)})"
                    )
                else:
                    logging.warning(f"No questions loaded for file source: {s_name}")

        return sources
