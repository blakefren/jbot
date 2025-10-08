from core.discord import run_discord_bot
from cfg.main import ConfigReader
from database.database import Database
from core.logger import Logger
from data.readers.question import Question
from data.readers.tsv import get_random_question
import os
import sys

def load_configs() -> ConfigReader:
    """Reads and returns the main configuration."""
    print("Reading configuration...")
    config = ConfigReader()
    # Adjust path for the new structure
    config.data["JBOT_DB_PATH"] = os.path.join(project_root, "database", "jbot.db")
    print("Configuration loaded.")
    return config


from data.loader import load_questions


# --- Main execution block ---
if __name__ == "__main__":
    # Setup
    # Add the project root to sys.path to allow imports from `data`
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sys.path.insert(0, project_root)

    config = load_configs()
    questions = load_questions(config)
    db_path = config.get("JBOT_DB_PATH", "jbot.db")
    db = Database(db_path)
    logger = Logger(db)

    # Print a single random question for verification
    if questions:
        print("\n--- Random Question ---")
        random_q = get_random_question(questions)
        print(random_q)
        print()

    # Start the game bot based on the messenger type
    messenger = config.get("JBOT_MESSENGER")
    if messenger == "discord":
        run_discord_bot(config, questions, db)
    else:
        print(f"Messenger '{messenger}' is not supported.")
