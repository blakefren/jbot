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


class ConfigReader:
    """
    A class to read configuration from environment variables.
    """

    def __init__(self):
        """
        Loads configuration from environment variables.
        """
        load_config()

    def get(self, key: str, default=None):
        """
        Retrieves a configuration value by key from environment variables.

        Args:
            key (str): The key to look for in the environment variables.
            default: The default value to return if the key is not found.

        Returns:
            The value associated with the key, or the default value if the key is not found.
        """
        return os.environ.get(key, default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        """
        Retrieves a boolean configuration value by key.

        Args:
            key (str): The key to look for in the configuration.
            default (bool): The default value if the key is not found.

        Returns:
            bool: The boolean value associated with the key.
        """
        value = self.get(key)
        if value is None:
            return default
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

        sources_config = self.get("JBOT_EXTRA_SOURCES")
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
