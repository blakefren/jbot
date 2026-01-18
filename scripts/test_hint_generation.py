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

    # 4. Create sample questions to get hints for
    riddle_question = Question(
        question="I have cities, but no houses; forests, but no trees; and water, but no fish. What am I?",
        answer="A map",
        category="Riddle",
    )

    trivia_question = Question(
        question="What is the largest planet in our solar system?",
        answer="Jupiter",
        category="Science",
    )

    # 5. Test both questions
    test_questions = [("Riddle", riddle_question), ("Trivia", trivia_question)]

    for question_type, sample_question in test_questions:
        logging.info(
            f"Requesting a hint for {question_type}: '{sample_question.question}'"
        )
        hint = question_selector.get_hint_from_gemini(sample_question)

        # Print the result
        if hint:
            print(f"\n--- Generated Hint ({question_type}) ---")
            print(f"Question: {sample_question.question}")
            print(f"Answer:   {sample_question.answer}")
            print(f"Hint:     {hint}")
            print("-----------------------\n")
        else:
            print(f"\n--- Failed to generate hint for {question_type}. ---")
            print("Check the logs for more details.\n")


if __name__ == "__main__":
    # To run this async script from the command line
    asyncio.run(main())
