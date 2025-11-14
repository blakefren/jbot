import datetime
from random import randint

from typing import Optional
from data.readers.question import Question
from zoneinfo import ZoneInfo
import logging
from src.core.gemini_manager import GeminiManager

# TODO: This should be handled more centrally
TIMEZONE = ZoneInfo("US/Pacific")


class QuestionSelector:
    """
    Manages the selection of trivia questions.
    Supports different modes for question selection.
    """

    def __init__(
        self,
        questions: list[Question],
        mode: str = "daily",
        gemini_manager: Optional[GeminiManager] = None,
    ):
        self.questions = questions
        self.mode = mode
        self.gemini_manager = gemini_manager
        if not questions:
            logging.warning("QuestionSelector initialized with no questions.")

    def get_riddle_from_gemini(self, difficulty: str) -> Optional[Question]:
        """
        Generates a riddle using the Gemini API and returns it as a Question object.
        """
        if not self.gemini_manager:
            raise ValueError("Gemini manager is not configured.")

        try:
            with open("prompts/riddle.txt", "r") as f:
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

    # TODO: prevent repeated questions.
    def get_question_for_today(self) -> Question:
        """
        Selects a question based on the current mode and date.
        """
        logging.debug(f"QuestionSelector.get_question_for_today")
        if not self.questions:
            raise ValueError("No questions available to select from.")

        if self.mode == "daily":
            # Use the date's ordinal number for a predictable daily question
            today = datetime.datetime.now(TIMEZONE).date()
            index = today.toordinal() % len(self.questions)
            return self.questions[index]
        elif self.mode == "random":
            return self.get_random_question()
        else:
            # TODO: Implement other modes like "themed", "random_without_repeat"
            raise NotImplementedError(
                f"Question selection mode '{self.mode}' is not yet implemented."
            )

    # TODO: limit to previous questions?
    def get_random_question(self) -> Question:
        """
        Returns a random question from the list.
        """
        if not self.questions:
            return None
        index = randint(0, len(self.questions) - 1)
        return self.questions[index]
