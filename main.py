from bot.discord import run_discord_bot
from cfg.main import ConfigReader
from database.database import Database
from database.logger import Logger
from bot.readers.question import Question
from bot.readers.tsv import (
    read_jeopardy_questions,
    get_random_question,
    read_knowledge_bowl_questions,
)
from bot.readers.csv_reader import (
    read_riddle_questions,
    read_riddle_with_hints_questions,
)
import os


def load_configs() -> ConfigReader:
    """Reads and returns the main configuration."""
    print("Reading configuration...")
    config = ConfigReader()
    print("Configuration loaded.")
    return config


def read_questions(config: ConfigReader) -> list[Question]:
    """
    Reads questions from the dataset specified in the config.
    """
    dataset = config.get("JBOT_QUESTION_DATASET")
    print(f"Reading '{dataset}' questions from file...")

    dataset_map = {
        "jeopardy": (
            read_jeopardy_questions,
            [
                config.get("JBOT_JEOPARDY_LOCAL_PATH"),
                config.get("JBOT_FINAL_JEOPARDY_SCORE_SUB"),
            ],
        ),
        "knowledge_bowl": (
            read_knowledge_bowl_questions,
            [config.get("JBOT_KNOWLEDGE_BOWL_LOCAL_PATH")],
        ),
        "riddles_small": (
            read_riddle_questions,
            [config.get("JBOT_RIDDLE_SMALL_LOCAL_PATH")],
        ),
        "riddles_with_hints": (
            read_riddle_with_hints_questions,
            [config.get("JBOT_RIDDLE_HINTS_LOCAL_PATH")],
        ),
    }

    if dataset in dataset_map:
        read_func, args = dataset_map[dataset]
        return read_func(*args)
    else:
        print(f"Unknown dataset: {dataset}")
        return []


# --- Main execution block ---
if __name__ == "__main__":
    # Setup
    config = load_configs()
    questions = read_questions(config)
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
