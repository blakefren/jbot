import os
import shutil
from dotenv import load_dotenv
import logging
import tomllib

# Define the paths for the .env files
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
ENV_PATH = os.path.join(BASE_DIR, ".env")
ENV_TEMPLATE_PATH = os.path.join(BASE_DIR, ".env.template")
SOURCES_TOML_PATH = os.path.join(BASE_DIR, "sources.toml")


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
        Loads configuration from environment variables and TOML sources.
        """
        load_config()
        self.validate_config()
        self._toml_config = self._load_toml_config()

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

    def _load_toml_config(self) -> dict:
        """
        Loads the TOML configuration file.
        Crashes gracefully with a clear error message if the file is missing or malformed.
        """
        if not os.path.exists(SOURCES_TOML_PATH):
            raise FileNotFoundError(
                f"Required configuration file not found: {SOURCES_TOML_PATH}\n"
                f"This file is required to start the bot. Please ensure it exists."
            )

        try:
            with open(SOURCES_TOML_PATH, "rb") as f:
                return tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(
                f"Malformed TOML configuration in {SOURCES_TOML_PATH}:\n{e}\n"
                f"Please fix the syntax errors in the configuration file."
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to load TOML configuration from {SOURCES_TOML_PATH}: {e}"
            )

    def get_dataset_path(self, dataset_name: str) -> str:
        """
        Retrieves the file path for a dataset from the TOML configuration.

        Args:
            dataset_name: The key name of the dataset in [datasets] section.

        Returns:
            The absolute path to the dataset file.

        Raises:
            KeyError: If the dataset name is not found in the configuration.
        """
        datasets = self._toml_config.get("datasets", {})
        if dataset_name not in datasets:
            raise KeyError(
                f"Dataset '{dataset_name}' not found in {SOURCES_TOML_PATH}.\n"
                f"Available datasets: {', '.join(datasets.keys())}"
            )

        relative_path = datasets[dataset_name]
        return os.path.join(BASE_DIR, relative_path)

    def parse_question_sources(self, gemini_manager=None):
        """
        Parses question sources from the TOML configuration and returns QuestionSource objects.
        Raises RuntimeError if no valid sources are found.
        """
        from data.readers.question_source import (
            GeminiQuestionSource,
            StaticQuestionSource,
        )
        from data.readers.tsv import read_jeopardy_questions
        from data.readers.csv_reader import (
            read_riddle_questions,
            read_riddle_with_hints_questions,
            read_knowledge_bowl_questions,
            read_simple_questions,
            read_general_trivia_questions,
        )

        sources = []
        source_configs = self._toml_config.get("source", [])

        if not source_configs:
            raise RuntimeError(
                f"No question sources defined in {SOURCES_TOML_PATH}.\n"
                f"At least one [[source]] must be configured for the bot to start."
            )

        for source_config in source_configs:
            s_name = source_config.get("name")
            s_type = source_config.get("type")
            s_weight = source_config.get("weight", 1.0)

            if not s_name or not s_type:
                logging.warning(
                    f"Invalid source config, missing name or type: {source_config}"
                )
                continue

            default_points = source_config.get("points")

            if s_type == "gemini":
                if not gemini_manager:
                    logging.warning(
                        f"Skipping Gemini source {s_name} because GeminiManager is not available."
                    )
                    continue

                difficulty = source_config.get("difficulty", "Medium")
                sources.append(
                    GeminiQuestionSource(
                        s_name, s_weight, gemini_manager, difficulty, default_points
                    )
                )
                logging.info(
                    f"Added Gemini source: {s_name} (weight={s_weight}, difficulty={difficulty}, points={default_points})"
                )

            elif s_type == "file":
                dataset_name = source_config.get("dataset")
                if not dataset_name:
                    logging.warning(f"File source {s_name} missing 'dataset' reference")
                    continue

                try:
                    dataset_path = self.get_dataset_path(dataset_name)
                except KeyError as e:
                    logging.error(f"Failed to load file source {s_name}: {e}")
                    raise  # Crash on missing dataset reference as specified

                reader_type = source_config.get("reader", "")
                questions = []

                # Load questions based on reader type
                if reader_type == "jeopardy":
                    difficulty = source_config.get("difficulty", "easy")
                    final_jeopardy_score = default_points if default_points else 300
                    questions = read_jeopardy_questions(
                        dataset_path,
                        difficulty=difficulty,
                        final_jeopardy_score=final_jeopardy_score,
                    )
                elif reader_type == "knowledge_bowl":
                    questions = read_knowledge_bowl_questions(dataset_path)
                elif reader_type == "riddle":
                    questions = read_riddle_questions(dataset_path)
                elif reader_type == "riddle_with_hints":
                    questions = read_riddle_with_hints_questions(dataset_path)
                elif reader_type == "simple":
                    category = source_config.get("category", dataset_name)
                    questions = read_simple_questions(dataset_path, category)
                elif reader_type == "general_trivia":
                    questions = read_general_trivia_questions(dataset_path)
                else:
                    logging.error(
                        f"File source {s_name} has unknown reader type: {reader_type}"
                    )
                    continue

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

        if not sources:
            raise RuntimeError(
                f"Failed to load any valid question sources from {SOURCES_TOML_PATH}.\n"
                f"Check your configuration and ensure at least one source is properly configured."
            )

        return sources
