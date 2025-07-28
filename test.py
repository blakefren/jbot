import os
import time
import discord
import asyncio

from bot.messenger import SMSBot
from bot.discord import test_discord_bot
from readers.main import ConfigReader
from readers.players import read_and_validate_contacts
from readers.tsv import read_jeopardy_questions, get_random_question

# MESSENGER = "sms"
MESSENGER = "discord"
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'cfg', 'main.cfg')
PLAYER_FILE_PATH = os.path.join(os.path.dirname(__file__), 'cfg', 'players.csv')


# --- Main execution block ---
if __name__ == "__main__":

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

    ### Read questions ###
    print("Reading Jeopardy! questions from the file...")
    all_questions = read_jeopardy_questions(config.get("JEOPARDY_LOCAL_PATH"))

    ### Print a single random question ###
    print("\n--- Random Question ---")
    random_q = get_random_question(all_questions)
    if random_q:
        print(
            f"  Category | Value: {random_q.get('category', 'N/A')} | {random_q.get('clue_value', 'N/A')}'"
        )
        print(f"  Answer: {random_q.get('answer', 'N/A')}")
        print(f"  Question: {random_q.get('question', 'N/A')}")
        print(f"  Air Date: {random_q.get('air_date', 'N/A')}")
    else:
        print("Could not retrieve a random question.")

    if MESSENGER == "sms":
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
            sms_bot.send_answer(to_phone_number=[c['discord_id'] for c in contacts], **random_q)

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

    elif MESSENGER == "discord":
        test_discord_bot(config, all_questions)
