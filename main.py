import os
import time
import discord
import asyncio

from bot.messenger import SMSBot
from bot.discord import run_discord_bot
from cfg.main import ConfigReader
from cfg.players import read_and_validate_contacts
from readers.tsv import read_jeopardy_questions, get_random_question

CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), "cfg", "main.cfg")
PLAYER_FILE_PATH = os.path.join(os.path.dirname(__file__), "cfg", "players.csv")


def load_configs():
    ### Read config ###
    print(f"Reading configuration from {CONFIG_FILE_PATH}...")
    config = ConfigReader(CONFIG_FILE_PATH)
    if config:
        print("Configuration loaded successfully:")

    ### Read players ###
    contacts = read_and_validate_contacts(PLAYER_FILE_PATH)
    if contacts:
        print("\n--- Valid Contacts Loaded ---")
        for contact in contacts:
            print(contact)
    else:
        print("\nNo valid contacts were loaded.")

def read_questions() -> List[Questions]
    ### Read questions ###
    print("Reading Jeopardy! questions from the file...")
    questions = read_jeopardy_questions(config.get("JEOPARDY_LOCAL_PATH"))
    return questions


# --- Main execution block ---
if __name__ == "__main__":
    # Setup
    load_configs()
    questions = read_questions()

    ### Print a single random question ###
    print("\n--- Random Question ---")
    random_q = get_random_question(questions)
    print(random_q)

    # Start game bot, depending on the messenger type.
    messenger = config.get("MESSENGER")
    if messenger == "sms":
        try:
            ### Messaging setup ###
            sms_bot = SMSBot(
                account_sid=config.get("TWILIO_ACCOUNT_SID"),
                auth_token=config.get("TWILIO_AUTH_TOKEN"),
                twilio_phone_number=config.get("FROM_NUMBER"),
            )

            ### Test: send a question ###
            sms_bot.send_question(**random_q)
            time.sleep(10)  # Wait for 2 seconds before sending the answer
            sms_bot.send_answer(
                to_phone_number=[c["discord_id"] for c in contacts], **random_q
            )

        except ValueError as e:
            print(f"\nConfiguration Error: {e}")
            print(
                "Please ensure your Twilio Account SID, Auth Token, and Phone Number are correctly set."
            )
            print(
                "You can set them in `/cfg/main.cfg` (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER)"
            )
        except Exception as e:
            print(f"\nAn unexpected error occurred during example usage: {e}")

    elif messenger == "discord":
        run_discord_bot(config, questions)
