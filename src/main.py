from core.discord import run_discord_bot
from cfg.main import ConfigReader
from db.database import Database
import logging
from src.logging_config import setup_logging
from src.core.data_manager import DataManager
from src.core.player_manager import PlayerManager
import os
import sys


def load_configs() -> ConfigReader:
    """Reads and returns the main configuration."""
    logging.info("Reading configuration...")
    config = ConfigReader()
    logging.info("Configuration loaded.")
    return config


# --- Main execution block ---
if __name__ == "__main__":
    # Setup
    setup_logging()
    # Add the project root to sys.path to allow imports from `data`
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sys.path.insert(0, project_root)

    config = load_configs()
    db_path = config.get("JBOT_DB_PATH")

    # Initialize database and data manager
    # NOTE: This is the ONLY place outside DataManager that should create a Database instance.
    # All database operations must go through DataManager methods.
    db = Database(db_path)
    data_manager = DataManager(db, config.get("JBOT_TIMEZONE"))
    player_manager = PlayerManager(data_manager)

    # Start the game bot based on the messenger type
    messenger = config.get("JBOT_MESSENGER")
    if messenger == "discord":
        run_discord_bot(config, data_manager, player_manager)
    else:
        logging.error(f"Messenger '{messenger}' is not supported.")
