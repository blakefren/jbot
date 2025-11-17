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

    def to_dict(self):
        """
        Converts the Question object to a dictionary.

        Returns:
            dict: A dictionary representation of the question.
        """
        return {
            "id": self.id,
            "question": self.question,
            "answer": self.answer,
            "category": self.category,
            "clue_value": self.clue_value,
            "hint": self.hint,
            "data_source": self.data_source,
            "metadata": self.metadata,
        }

    def get_metadata(self, key: str, default=None):
        """
        Retrieves a specific metadata value by key.

        Args:
            key (str): The metadata key to retrieve.
            default: The default value to return if the key is not found.

        Returns:
            The metadata value associated with the given key, or the default value if the key is not found.
        """
        return self.metadata.get(key, default)

    @classmethod
    def from_dict(cls, data):
        """
        Creates a Question object from a dictionary.

        Args:
            data (dict): A dictionary containing question data.

        Returns:
            Question: An instance of Question.
        """
        return cls(
            question=data["question"],
            answer=data["answer"],
            category=data["category"],
            clue_value=data["clue_value"],
            hint=data.get("hint"),
            data_source=data.get("data_source", "unknown"),
            metadata=data.get("metadata", {}),
        )


# --- Example Usage ---
if __name__ == "__main__":
    # Create a Question instance
    q1 = Question(
        question="This ancient civilization built the Great Pyramid of Giza.",
        answer="Egypt",
        category="WORLD HISTORY",
        clue_value=200,
        hint="They were ruled by Pharaohs.",
        data_source="j-archive.com",
        metadata={"air_date": "2023-01-15", "episode": 1234},
    )

    print("--- Question 1 Details ---")
    print(q1)

    # Convert to dictionary
    q1_dict = q1.to_dict()
    print("\n--- Question 1 as Dictionary ---")
    print(q1_dict)

    # Create a Question instance from a dictionary
    q2_data = {
        "question": "The capital of France.",
        "answer": "Paris",
        "category": "GEOGRAPHY",
        "clue_value": 400,
        "hint": "City of Love",
        "data_source": "custom_set",
        "metadata": {"difficulty": "easy"},
    }
    q2 = Question.from_dict(q2_data)
    print("\n--- Question 2 Details (from dict) ---")
    print(q2)

    # Test with minimal data (defaults)
    q3 = Question(
        question="A primary color.",
        answer="Red",
        category="COLORS",
        clue_value=100,
    )
    print("\n--- Question 3 Details (minimal) ---")
    print(q3)

    # Test invalid input
    print("\n--- Testing Invalid Input ---")
    try:
        Question(question="", answer="A", category="B", clue_value=100)
    except ValueError as e:
        print(f"Error creating question: {e}")

    try:
        Question(question="A", answer="B", category="C", clue_value=-50)
    except ValueError as e:
        print(f"Error creating question: {e}")
