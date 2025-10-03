from bot.discord import run_discord_bot
from cfg.main import ConfigReader
from database.logger import Logger
from readers.question import Question
from readers.tsv import (
    read_jeopardy_questions,
    get_random_question,
    read_knowledge_bowl_questions,
)
from readers.csv_reader import (
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
    dataset = config.get("QUESTION_DATASET")
    print(f"Reading '{dataset}' questions from file...")

    dataset_map = {
        "jeopardy": (
            read_jeopardy_questions,
            [
                config.get("JEOPARDY_LOCAL_PATH"),
                config.get("FINAL_JEOPARDY_SCORE_SUB"),
            ],
        ),
        "knowledge_bowl": (
            read_knowledge_bowl_questions,
            [config.get("KNOWLEDGE_BOWL_LOCAL_PATH")],
        ),
        "riddles_small": (
            read_riddle_questions,
            [config.get("RIDDLE_SMALL_LOCAL_PATH")],
        ),
        "riddles_with_hints": (
            read_riddle_with_hints_questions,
            [config.get("RIDDLE_HINTS_LOCAL_PATH")],
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
    db_path = os.path.join(os.path.dirname(__file__), "database", "jbot.db")
    logger = Logger(db_path)

    # Print a single random question for verification
    if questions:
        print("\n--- Random Question ---")
        random_q = get_random_question(questions)
        print(random_q)
        print()

    # Start the game bot based on the messenger type
    messenger = config.get("MESSENGER")
    if messenger == "discord":
        run_discord_bot(config, questions, logger)
    else:
        print(f"Messenger '{messenger}' is not supported.")
