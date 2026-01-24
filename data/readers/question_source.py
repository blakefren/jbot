from abc import ABC, abstractmethod
from data.readers.question import Question
import random
import logging
import os

# Project root for file paths
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class QuestionSource(ABC):
    """
    Abstract base class for a source of questions.
    """

    def __init__(self, name: str, weight: float, default_points: int | None = None):
        self.name = name
        self.weight = weight
        self.default_points = default_points

    @abstractmethod
    def get_question(
        self, exclude_hashes: set[str] = None, previous_answers: list[str] = None
    ) -> Question | None:
        """
        Retrieves a question from this source.
        """
        pass


class StaticQuestionSource(QuestionSource):
    """
    A source that selects from a pre-loaded list of questions.
    """

    def __init__(
        self,
        name: str,
        weight: float,
        questions: list[Question],
        default_points: int | None = None,
    ):
        super().__init__(name, weight, default_points)
        self.questions = questions

    def get_question(
        self, exclude_hashes: set[str] = None, previous_answers: list[str] = None
    ) -> Question | None:
        if not self.questions:
            logging.warning(f"StaticQuestionSource '{self.name}' has no questions.")
            return None

        available = self.questions
        if exclude_hashes:
            available = [q for q in self.questions if str(q.id) not in exclude_hashes]
            if not available:
                logging.warning(
                    f"Source '{self.name}' exhausted (all excluded). Using full pool."
                )
                available = self.questions

        question = random.choice(available)
        if self.default_points is not None:
            question.clue_value = self.default_points
        return question


class GeminiQuestionSource(QuestionSource):
    """
    A source that generates questions using Gemini.
    """

    CATEGORIES = [
        "Nature",
        "Technology",
        "Home",
        "Food",
        "History",
        "Science",
        "Animals",
        "Geography",
        "Music",
        "Tools",
        "Space",
        "Literature",
        "Sports",
    ]

    def __init__(
        self,
        name: str,
        weight: float,
        gemini_manager,
        difficulty: str = "Medium",
        default_points: Optional[int] = None,
    ):
        super().__init__(name, weight, default_points)
        self.gemini_manager = gemini_manager
        self.difficulty = difficulty

    def get_question(
        self, exclude_hashes: set[str] = None, previous_answers: list[str] = None
    ) -> Optional[Question]:
        if not self.gemini_manager:
            logging.error(f"GeminiQuestionSource '{self.name}' has no GeminiManager.")
            return None

        try:
            riddle_prompt_path = os.path.join(_PROJECT_ROOT, "prompts", "riddle.txt")
            with open(riddle_prompt_path, "r", encoding="utf-8") as f:
                prompt_template = f.read()
        except FileNotFoundError:
            logging.error("Riddle prompt file not found.")
            return None

        # Select a random category
        category = random.choice(self.CATEGORIES)

        # Build exclusions string
        exclusions_text = ""
        if previous_answers:
            exclusions_text = "Do not use any of the following answers: " + ", ".join(
                previous_answers
            )

        prompt = prompt_template.replace(
            '[Insert Your Desired Difficulty Here, e.g., "Medium"]', self.difficulty
        )
        prompt = prompt.replace("[Insert Category Here]", category)
        prompt = prompt.replace("[Insert Exclusions Here]", exclusions_text)

        # Default temperature for creativity
        generation_config = {"temperature": 1.0}

        response_text = self.gemini_manager.generate_content(
            prompt, generation_config=generation_config
        )

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
                category=f"Riddle ({self.difficulty.lower()}) - {category}",
                hint=hint,
                data_source=f"gemini_{self.difficulty.lower()}",
                clue_value=self.default_points if self.default_points else 100,
            )
        except (StopIteration, IndexError) as e:
            logging.error(
                f"Failed to parse riddle from Gemini response: {e}\nResponse: {response_text}"
            )
            return None
