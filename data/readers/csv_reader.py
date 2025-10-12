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
                        question=row["QUESTIONS"],
                        answer=row["ANSWERS"],
                        category="Riddle",
                        clue_value=100,  # Default value for riddles
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
                        question=row["Riddle"],
                        answer=row["Answer"],
                        category="Riddle",
                        clue_value=100,  # Default value for riddles
                        hint=row["Hint"],
                        data_source="Riddles with Hints",
                    )
                )
    except FileNotFoundError:
        logging.error(f"The file at {file_path} was not found.")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    return questions
