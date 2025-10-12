import datetime
from random import randint
from data.readers.question import Question
from zoneinfo import ZoneInfo
import logging

# TODO: This should be handled more centrally
TIMEZONE = ZoneInfo("US/Pacific")


class QuestionSelector:
    """
    Manages the selection of trivia questions.
    Supports different modes for question selection.
    """

    def __init__(self, questions: list[Question], mode: str = "daily"):
        self.questions = questions
        self.mode = mode
        if not questions:
            logging.warning("QuestionSelector initialized with no questions.")

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

    def get_random_question(self) -> Question:
        """
        Returns a random question from the list.
        """
        if not self.questions:
            return None
        index = randint(0, len(self.questions) - 1)
        return self.questions[index]
