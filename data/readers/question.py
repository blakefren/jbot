import hashlib


class Question:
    """
    A class to represent a single trivia question and its associated data.
    """

    def __init__(
        self,
        question: str,
        answer: str,
        category: str,
        clue_value: int = 100,
        hint: str = None,
        data_source: str = "unknown",
        metadata: dict = None,
        is_valid: bool = True,
    ):
        """
        Initializes a Question object.

        Args:
            question (str): The text of the Jeopardy! question (the clue).
            answer (str): The correct answer to the question.
            category (str): The category of the question (e.g., "WORLD HISTORY").
            clue_value (int, optional): The point value of the question (e.g., 200, 400). Defaults to 100.
            hint (str, optional): A hint for the question. Defaults to None.
            data_source (str, optional): The source from which the question was obtained
                                         (e.g., "j-archive.com", "custom_set"). Defaults to "unknown".
            metadata (dict, optional): A dictionary for any additional, flexible metadata
                                       related to the question (e.g., air_date, episode_number).
                                       Defaults to an empty dictionary if None is provided.
            is_valid (bool, optional): Whether the question is considered valid. Defaults to True.
        """
        if not isinstance(question, str) or not question:
            raise ValueError("Question must be a non-empty string.")
        if not isinstance(answer, str) or not answer:
            raise ValueError("Answer must be a non-empty string.")
        if not isinstance(category, str) or not category:
            raise ValueError("Category must be a non-empty string.")
        if not isinstance(clue_value, int) or clue_value < 0:
            raise ValueError("Clue value must be a positive integer.")

        self.question = question
        self.answer = answer
        self.category = category
        self.clue_value = clue_value
        self.hint = hint
        self.data_source = data_source
        self.metadata = metadata if metadata is not None else {}
        self.is_valid = is_valid
        # Hash the question and answer to create a unique ID
        # https://stackoverflow.com/questions/2511058/persistent-hashing-of-strings-in-python
        self.id = int(
            hashlib.md5(
                f"{question.lower()} {answer.lower()}".encode("utf-8")
            ).hexdigest(),
            16,
        )

    def __str__(self):
        """
        Returns a human-readable string representation of the Question.
        """
        parts = [
            f"ID: {self.id}",
            f"Category: {self.category}",
            f"Value: ${self.clue_value}",
            f"Question: {self.question}",
            f"Answer: {self.answer}",
        ]
        if self.hint:
            parts.append(f"Hint: {self.hint}")
        parts.append(f"Source: {self.data_source}")
        return "\\n".join(parts)
