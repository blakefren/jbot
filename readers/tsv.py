import csv
import random


def read_jeopardy_questions(file_path: str):
    """
    Reads a TSV file containing Jeopardy! questions and returns them as a list of dictionaries.

    Args:
        file_path (str): The full path to the TSV file.

    Returns:
        list: A list of dictionaries, where each dictionary represents a question.
              Returns an empty list if the file is not found or an error occurs.
    """
    questions = []
    try:
        with open(file_path, "r", encoding="utf-8") as tsvfile:
            # The csv.reader can handle TSV by specifying the delimiter as a tab character.
            # DictReader is used to map the information in each row to a dictionary with the column headers as keys.
            reader = csv.DictReader(tsvfile, delimiter="\t")
            for row in reader:
                questions.append(row)

    except FileNotFoundError:
        print(f"Error: The file at {file_path} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

    return questions


def get_random_question(questions: list):
    """
    Selects a random question from the list of questions.

    Args:
        questions (list): A list of question dictionaries.

    Returns:
        dict: A single dictionary representing a random question, or None if the list is empty.
    """
    if not questions:
        return None
    return random.choice(questions)
