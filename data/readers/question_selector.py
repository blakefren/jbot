import datetime
import random
from typing import Optional
from data.readers.question import Question
from data.readers.question_source import QuestionSource, StaticQuestionSource
from zoneinfo import ZoneInfo
import logging
import os
from src.core.gemini_manager import GeminiManager

# Project root for file paths
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# TODO: This should be handled more centrally
TIMEZONE = ZoneInfo("US/Pacific")


class QuestionSelector:
    """
    Manages the selection of trivia questions.
    Supports different modes for question selection.
    """

    def __init__(
        self,
        sources: list[QuestionSource] = None,
        questions: list[Question] = None,
        gemini_manager: Optional[GeminiManager] = None,
    ):
        self.gemini_manager = gemini_manager
        self.sources = sources or []

        # Legacy support: if questions are passed, treat as a default source
        if questions:
            self.sources.append(StaticQuestionSource("default", 100.0, questions))

        if not self.sources:
            logging.warning("QuestionSelector initialized with no sources.")

    def get_riddle_from_gemini(self, difficulty: str) -> Optional[Question]:
        """
        Generates a riddle using the Gemini API and returns it as a Question object.
        """
        if not self.gemini_manager:
            raise ValueError("Gemini manager is not configured.")

        try:
            riddle_prompt_path = os.path.join(_PROJECT_ROOT, "prompts", "riddle.txt")
            with open(riddle_prompt_path, "r", encoding="utf-8") as f:
                prompt = f.read()
        except FileNotFoundError:
            logging.error("Riddle prompt file not found.")
            return None

        prompt = prompt.replace(
            '[Insert Your Desired Difficulty Here, e.g., "Medium"]', difficulty
        )

        response_text = self.gemini_manager.generate_content(prompt)

        if not response_text:
            logging.error("Failed to get response from Gemini.")
            return None

        # Parse the response
        try:
            lines = response_text.strip().split("\n")
            riddle_line = next(line for line in lines if line.startswith("Riddle:"))
            hint_line = next(line for line in lines if line.startswith("Hint:"))
            answer_line = next(line for line in lines if line.startswith("Answer:"))

            riddle = riddle_line.replace("Riddle:", "").strip()
            hint = hint_line.replace("Hint:", "").strip()
            answer = answer_line.replace("Answer:", "").strip()

            return Question(
                question=riddle,
                answer=answer,
                category="Riddle",
                hint=hint,
                data_source="gemini",
            )
        except (StopIteration, IndexError) as e:
            logging.error(
                f"Failed to parse riddle from Gemini response: {e}\nResponse: {response_text}"
            )
            return None

    def get_hint_from_gemini(self, question: Question) -> Optional[str]:
        """
        Generates a hint for a given question using the Gemini API.
        """
        if not self.gemini_manager:
            raise ValueError("Gemini manager is not configured.")

        try:
            hint_prompt_path = os.path.join(_PROJECT_ROOT, "prompts", "hint.txt")
            with open(hint_prompt_path, "r", encoding="utf-8") as f:
                prompt = f.read()
        except FileNotFoundError:
            logging.error("Hint prompt file not found.")
            return None

        prompt = prompt.replace("[Insert your riddle here]", question.question)
        prompt = prompt.replace("[Insert your answer here]", question.answer)

        response_text = self.gemini_manager.generate_content(prompt)

        if not response_text:
            logging.error("Failed to get response from Gemini for hint.")
            return None

        # Parse the response
        try:
            lines = response_text.strip().split("\n")
            hint_line = next(line for line in lines if line.startswith("Hint:"))
            hint = hint_line.replace("Hint:", "").strip()
            return hint
        except StopIteration:
            logging.error(
                f"Failed to parse hint from Gemini response. Response: {response_text}"
            )
            return None

    def validate_question(self, question: Question) -> bool:
        """
        Uses Gemini to check if a question is valid (e.g. not broken or malformed).
        Returns True if valid, False if invalid.
        """
        if not self.gemini_manager:
            return True  # Assume valid if no LLM

        try:
            prompt_path = os.path.join(
                _PROJECT_ROOT, "prompts", "validate_question.txt"
            )
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_template = f.read()
        except FileNotFoundError:
            logging.error("Validate question prompt file not found.")
            return True

        prompt = prompt_template.replace("[Insert Question Here]", question.question)
        prompt = prompt.replace("[Insert Answer Here]", question.answer)

        response = self.gemini_manager.generate_content(prompt)
        if not response:
            return True  # Fail open

        cleaned_response = response.strip().upper()
        # The prompt asks: "Is this question broken or invalid? Respond with only YES..."
        # So YES means it IS broken/invalid.
        if "YES" in cleaned_response:
            logging.info(f"Detected invalid question (by LLM): {question.question}")
            return False

        return True

    def get_random_question(self, exclude_hashes: set[str] = None) -> Question:
        """
        Returns a random question from the configured sources.

        Args:
            exclude_hashes: Set of question hashes (as strings) to exclude from selection.

        Returns:
            A randomly selected Question, or None if no questions are available.
        """
        logging.debug(f"QuestionSelector.get_random_question")
        if not self.sources:
            return None

        # Weighted selection of source
        total_weight = sum(s.weight for s in self.sources)
        if total_weight <= 0:
            logging.warning("Total weight of sources is 0. Picking random source.")
            source = random.choice(self.sources)
        else:
            pick = random.uniform(0, total_weight)
            current = 0
            source = self.sources[-1]  # Default to last
            for s in self.sources:
                current += s.weight
                if pick <= current:
                    source = s
                    break

        logging.info(f"Selected question source: {source.name}")
        question = source.get_question(exclude_hashes)

        if not question:
            logging.warning(f"Source {source.name} returned no question.")
            return None

        # Validate it
        if self.validate_question(question):
            question.is_valid = True
        else:
            question.is_valid = False

        return question
