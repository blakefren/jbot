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
    Initializes the necessary components and tests the question validator.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")

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
    # We don't need to load actual questions for this test
    question_selector = QuestionSelector(questions=[], gemini_manager=gemini_manager)

    # 4. Define test cases
    test_cases = [
        {
            "question": "What is the capital of France?",
            "answer": "Paris",
            "expected_valid": True,
            "description": "Valid simple question",
        },
        {
            "question": "Which of the following is a mammal?",
            "answer": "Whale",
            "expected_valid": False,
            "description": "Missing options ('Which of the following...')",
        },
        {
            "question": "Select the correct year: 1990, 2000, 2010.",
            "answer": "2000",
            "expected_valid": False,
            "description": "Invalid question (ambiguous/incomplete despite having options)",
        },
        {
            "question": "asdf jkl;",
            "answer": "qwerty",
            "expected_valid": False,
            "description": "Nonsense/Gibberish",
        },
        {
            "question": "What is the square root of 144?",
            "answer": "Abraham Lincoln",
            "expected_valid": False,
            "description": "Answer doesn't make sense for the question",
        },
    ]

    print("\n--- Starting Question Validator Test ---\n")

    passed_count = 0
    for i, case in enumerate(test_cases):
        q = Question(question=case["question"], answer=case["answer"], category="Test")

        print(f"Test Case {i+1}: {case['description']}")
        print(f"  Q: {q.question}")
        print(f"  A: {q.answer}")

        # The validate_question method returns True if valid, False if invalid/broken
        is_valid = question_selector.validate_question(q)

        result_str = "VALID" if is_valid else "INVALID/BROKEN"
        expected_str = "VALID" if case["expected_valid"] else "INVALID/BROKEN"

        if is_valid == case["expected_valid"]:
            print(f"  Result: {result_str} (MATCH)")
            passed_count += 1
        else:
            print(f"  Result: {result_str} (MISMATCH - Expected {expected_str})")

        print("-" * 40)

    print(f"\nTest Complete. Passed {passed_count}/{len(test_cases)} cases.")


if __name__ == "__main__":
    asyncio.run(main())
