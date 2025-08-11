from bot.discord import run_discord_bot
from cfg.main import ConfigReader
from cfg.players import read_and_validate_contacts
from log.logger import Logger
from readers.question import Question
from readers.tsv import read_jeopardy_questions, get_random_question, read_knowledge_bowl_questions


def load_configs() -> ConfigReader:
    ### Read config ###
    print(f"Reading configuration...")
    config = ConfigReader()
    if config:
        print("Configuration loaded successfully:")
    return config


def load_players() -> list[dict]:
    ### Read players ###
    contacts = read_and_validate_contacts()
    if contacts:
        print("\n--- Valid Contacts Loaded ---")
        for contact in contacts:
            print(contact)
    else:
        print("\nNo valid contacts were loaded.")
    return contacts


def read_questions(dataset: str) -> list[Question]:
    """
    Reads questions from the specified dataset.

    Args:
        dataset (str): The name of the dataset to use (e.g., "jeopardy" or "knowledge_bowl").

    Returns:
        list[Question]: A list of Question objects.
    """
    print(f"Reading {dataset} questions from the file...")
    if dataset == "jeopardy":
        return read_jeopardy_questions(
            config.get("JEOPARDY_LOCAL_PATH"), config.get("FINAL_JEOPARDY_SCORE_SUB")
        )
    elif dataset == "knowledge_bowl":
        return read_knowledge_bowl_questions(config.get("KNOWLEDGE_BOWL_LOCAL_PATH"))
    else:
        print(f"Unknown dataset: {dataset}")
        return []


# --- Main execution block ---
if __name__ == "__main__":
    # Setup
    config = load_configs()
    players = load_players()
    questions = read_questions(config.get("QUESTION_DATASET"))
    logger = Logger()

    ### Print a single random question ###
    print("\n--- Random Question ---")
    random_q = get_random_question(questions)
    print(random_q)
    print()

    # Start game bot, depending on the messenger type.
    messenger = config.get("MESSENGER")
    if messenger == "discord":
        run_discord_bot(config, questions, logger)
    else:
        pass
