import asyncio
import os
import sys
import logging

# Add the project root to the Python path to allow for absolute imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from src.cfg.main import ConfigReader
from src.core.gemini_manager import GeminiManager
from data.readers.question_selector import QuestionSelector


async def main():
    """
    Initializes the necessary components and tests the riddle generation.
    """
    logging.basicConfig(level=logging.INFO)

    # 1. Initialize ConfigReader to get API key
    try:
        config = ConfigReader()
        api_key = config.get_gemini_api_key()
        if not api_key:
            logging.error("GEMINI_API_KEY not found in environment variables.")
            return
    except Exception as e:
        logging.error(f"Failed to read configuration: {e}")
        return

    # 2. Initialize GeminiManager
    gemini_manager = GeminiManager(api_key=api_key)

    # 3. Initialize QuestionSelector with the GeminiManager
    # We pass an empty list of questions as we are only testing the API call.
    question_selector = QuestionSelector(questions=[], gemini_manager=gemini_manager)

    # 4. Call the new method with a desired difficulty
    difficulty = "Hard"
    logging.info(f"Requesting a '{difficulty}' riddle from Gemini...")
    riddle_question = question_selector.get_riddle_from_gemini(difficulty)

    # 5. Print the result
    if riddle_question:
        print("\n--- Generated Riddle ---")
        print(f"Question: {riddle_question.question}")
        print(f"Answer:   {riddle_question.answer}")
        print(f"Hint:     {riddle_question.hint}")
        print(f"Category: {riddle_question.category}")
        print("-----------------------\n")
    else:
        print("\n--- Failed to generate riddle. ---")
        print("Check the logs for more details.\n")


if __name__ == "__main__":
    # To run this async script from the command line
    asyncio.run(main())
