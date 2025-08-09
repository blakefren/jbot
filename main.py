from bot.discord import run_discord_bot
from cfg.main import ConfigReader
from cfg.players import read_and_validate_contacts
from readers.question import Question
from readers.tsv import read_jeopardy_questions, get_random_question


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


def read_questions() -> list[Question]:
    ### Read questions ###
    print("Reading Jeopardy! questions from the file...")
    questions = read_jeopardy_questions(
        config.get("JEOPARDY_LOCAL_PATH"), config.get("FINAL_JEOPARDY_SCORE_SUB")
    )
    return questions


# --- Main execution block ---
if __name__ == "__main__":
    # Setup
    config = load_configs()
    players = load_players()
    questions = read_questions()

    ### Print a single random question ###
    print("\n--- Random Question ---")
    random_q = get_random_question(questions)
    print(random_q)
    print()

    # Start game bot, depending on the messenger type.
    messenger = config.get("MESSENGER")
    if messenger == "discord":
        run_discord_bot(config, questions)
    else:
        pass
