from core.discord import run_discord_bot
from cfg.main import ConfigReader
from db.database import Database
import logging
from src.logging_config import setup_logging
from src.core.data_manager import DataManager
from data.readers.question import Question
from data.readers.tsv import get_random_question
import os
import sys

def load_configs() -> ConfigReader:
    """Reads and returns the main configuration."""
    logging.info("Reading configuration...")
    config = ConfigReader()
    logging.info("Configuration loaded.")
    return config


from data.loader import load_questions


# --- Main execution block ---
if __name__ == "__main__":
    # Setup
    setup_logging()
    # Add the project root to sys.path to allow imports from `data`
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sys.path.insert(0, project_root)

    config = load_configs()
    questions = load_questions(config)
    db_path = config.get("JBOT_DB_PATH", "jbot.db")
    db = Database(db_path)
    data_manager = DataManager(db)

    # Print a single random question for verification
    if questions:
        logging.info("--- Random Question ---")
        random_q = get_random_question(questions)
        logging.info(random_q)
        logging.info("-----------------------")

    # Start the game bot based on the messenger type
    messenger = config.get("JBOT_MESSENGER")
    if messenger == "discord":
        run_discord_bot(config, questions, db, data_manager)
    else:
        logging.error(f"Messenger '{messenger}' is not supported.")
