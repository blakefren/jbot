import datetime

from random import randint
from readers.question import Question  # Assuming this is your JeopardyQuestion class
from zoneinfo import ZoneInfo

# TODO: read timezone from config
TIMEZONE = ZoneInfo("US/Pacific")


class QuestionSelector:
    """
    Manages the selection of Jeopardy! questions.
    Supports different modes for question selection.
    """

    def __init__(self, questions: list[Question], mode: str = "daily"):
        self.questions = questions
        self.mode = mode
        if not questions:
            print("Warning: QuestionSelector initialized with no questions.")

    def get_question_for_today(self) -> Question:
        """
        Selects a question based on the current mode and date.
        
        Args:
            current_date (datetime.date): The date for which to get the question.
        """
        if not self.questions:
            raise ValueError("No questions available to select from.")
        if self.mode == "daily":
            # Select a question based on the date's ordinal number for predictable daily questions
            current_time = datetime.datetime.now(TIMEZONE)
            index = current_time.date().toordinal() % len(self.questions)
            return self.questions[index]
        else:
            # TODO: Implement other modes, e.g., "themed", "random_without_repeat", etc.
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
