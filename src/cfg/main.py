import os
import shutil
from dotenv import load_dotenv
import logging

# Define the paths for the .env files
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
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

    def get_bool(self, key: str) -> bool:
        """
        Retrieves a boolean configuration value by key.

        Args:
            key (str): The key to look for in the configuration.

        Returns:
            bool: The boolean value associated with the key.
        """
        value = self.get(key)
        if value is None:
            raise KeyError(f"Key '{key}' not found in environment variables.")
        return value.lower() in ("true", "1", "t", "y", "yes")
