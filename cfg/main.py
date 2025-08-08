import os

CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), "main.cfg")


class ConfigReader:
    """
    A class to read configuration files and retrieve settings.
    """

    def __init__(self):
        """
        Reads a configuration file with 'key: value' format.

        Returns:
            dict: A dictionary of the configuration settings.
                Returns an empty dictionary if the file is not found or an error occurs.
        """
        file_path = CONFIG_FILE_PATH
        self.config = {}
        try:
            with open(file_path, "r", encoding="utf-8") as configfile:
                for line in configfile:
                    # Skip empty lines or lines that are comments (e.g., starting with #)
                    if line.strip() and not line.strip().startswith("#"):
                        # Split only on the first occurrence of ':'
                        parts = line.strip().split(":", 1)
                        if len(parts) == 2:
                            key = parts[0].strip()
                            value = parts[1].strip()
                            self.config[key] = value
        except FileNotFoundError:
            print(f"Error: The config file at {file_path} was not found.")
        except Exception as e:
            print(f"An error occurred while reading the config file: {e}")

    def get(self, key: str):
        """
        Retrieves a configuration value by key. Throws error if the key is not found.

        Args:
            key (str): The key to look for in the configuration.

        Returns:
            The value associated with the key, or the default value if the key is not found.
        """
        if key not in self.config:
            raise KeyError(f"Configuration key '{key}' not found.")
        else:
            return self.config.get(key, None)

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
            return False
        return value.lower() in ("true", "1", "t", "y", "yes")
