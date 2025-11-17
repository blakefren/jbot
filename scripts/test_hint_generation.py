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
from data.readers.question import Question


async def main():
    """
    Initializes the necessary components and tests the hint generation.
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
    question_selector = QuestionSelector(questions=[], gemini_manager=gemini_manager)

    # 4. Create a sample question to get a hint for
    sample_question = Question(
        question="I have cities, but no houses; forests, but no trees; and water, but no fish. What am I?",
        answer="A map",
        category="Riddle",
    )

    logging.info(f"Requesting a hint for the question: '{sample_question.question}'")
    hint = question_selector.get_hint_from_gemini(sample_question)

    # 5. Print the result
    if hint:
        print("\n--- Generated Hint ---")
        print(f"Question: {sample_question.question}")
        print(f"Answer:   {sample_question.answer}")
        print(f"Hint:     {hint}")
        print("-----------------------\n")
    else:
        print("\n--- Failed to generate hint. ---")
        print("Check the logs for more details.\n")


if __name__ == "__main__":
    # To run this async script from the command line
    asyncio.run(main())
