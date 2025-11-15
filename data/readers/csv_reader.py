import csv
import logging
from data.readers.question import Question


def read_riddle_questions(file_path: str) -> list[Question]:
    """
    Reads riddle questions from a CSV file.

    Args:
        file_path (str): The path to the CSV file.

    Returns:
        list[Question]: A list of Question objects.
    """
    questions = []
    try:
        with open(file_path, mode="r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                questions.append(
                    Question(
                        question=row.get("QUESTIONS"),
                        answer=row.get("ANSWERS"),
                        category="Riddle",
                        clue_value=100,  # Default value for riddles
                        hint=row.get("Hint"),
                        data_source="Riddles (small)",
                    )
                )
    except FileNotFoundError:
        logging.error(f"The file at {file_path} was not found.")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    return questions


def read_riddle_with_hints_questions(file_path: str) -> list[Question]:
    """
    Reads riddle questions with hints from a CSV file.

    Args:
        file_path (str): The path to the CSV file.

    Returns:
        list[Question]: A list of Question objects.
    """
    questions = []
    try:
        with open(file_path, mode="r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                questions.append(
                    Question(
                        question=row.get("Riddle"),
                        answer=row.get("Answer"),
                        category="Riddle",
                        clue_value=100,  # Default value for riddles
                        hint=row.get("Hint"),
                        data_source="Riddles with Hints",
                    )
                )
    except FileNotFoundError:
        logging.error(f"The file at {file_path} was not found.")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    return questions


def read_knowledge_bowl_questions(file_path: str) -> list[Question]:
    """
    Reads knowledge bowl questions from a CSV file.

    Args:
        file_path (str): The path to the CSV file.

    Returns:
        list[Question]: A list of Question objects.
    """
    questions = []
    try:
        with open(file_path, mode="r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                questions.append(
                    Question(
                        question=row.get("Question"),
                        answer=row.get("Answer"),
                        category=row.get("Subject"),
                        clue_value=100,  # Default value
                        hint=row.get("Hint"),
                        data_source="Knowledge Bowl",
                    )
                )
    except FileNotFoundError:
        logging.error(f"The file at {file_path} was not found.")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    return questions


def read_simple_questions(file_path: str, source: str) -> list[Question]:
    """
    Reads simple questions from a CSV file with 'Question' and 'Answer' columns.

    Args:
        file_path (str): The path to the CSV file.
        source (str): The name of the data source.

    Returns:
        list[Question]: A list of Question objects.
    """
    questions = []
    try:
        with open(file_path, mode="r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                questions.append(
                    Question(
                        question=row.get("Question"),
                        answer=row.get("Answer"),
                        category=source,
                        clue_value=100,  # Default value
                        hint=row.get("Hint"),
                        data_source=source,
                    )
                )
    except FileNotFoundError:
        logging.error(f"The file at {file_path} was not found.")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    return questions


def read_general_trivia_questions(file_path: str) -> list[Question]:
    """
    Reads general trivia questions from a CSV file.

    Args:
        file_path (str): The path to the CSV file.

    Returns:
        list[Question]: A list of Question objects.
    """
    questions = []
    try:
        with open(file_path, mode="r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                questions.append(
                    Question(
                        question=row.get("Question"),
                        answer=row.get("Answer"),
                        category=row.get("Category"),
                        clue_value=100,  # Default value
                        hint=row.get("Hint"),
                        data_source="General Trivia",
                    )
                )
    except FileNotFoundError:
        logging.error(f"The file at {file_path} was not found.")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    return questions
