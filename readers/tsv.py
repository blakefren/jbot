import csv
import random

from readers.question import Question


def parse_value(value: str) -> int:
    """
    Parses a string value to an integer, removing any dollar sign.

    Args:
        value (str): The string value to parse.

    Returns:
        int: The parsed integer value.
    """
    return int(value.replace("$", "").replace(",", "")) if value else 0


def read_jeopardy_questions(
    file_path: str, final_jeopardy_score: int = 0
) -> list[Question]:
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
                metadata = {
                    "round": row.get("round", "N/A"),
                    "air_date": row.get("air_date", "N/A"),
                    "daily_double": row.get("daily_double_value", 0),
                }
                # Give final jeopardy a real score.
                clue_value = parse_value(row.get("clue_value", 0))
                final_jeopardy = metadata.get("round", 0) == 3
                clue_value_adj = final_jeopardy_score if final_jeopardy else clue_value
                # Jeopardy! has the answer and question swapped.
                questions.append(
                    Question(
                        question=row.get("answer", "N/A"),
                        answer=row.get("question", "N/A"),
                        category=row.get("category", "N/A"),
                        clue_value=clue_value_adj,
                        data_source="Jeopardy!",
                        metadata=metadata,
                    )
                )

    except FileNotFoundError:
        print(f"Error: The file at {file_path} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

    return questions


def read_knowledge_bowl_questions(file_path: str) -> list[Question]:
    """
    Reads a TSV file containing Knowledge Bowl questions and returns them as a list of Questions.

    Args:
        file_path (str): The full path to the TSV file.

    Returns:
        list: A list of Question objects.
              Returns an empty list if the file is not found or an error occurs.
    """
    questions = []
    try:
        with open(file_path, "r", encoding="utf-8") as tsvfile:
            reader = csv.DictReader(tsvfile, delimiter="\t")
            for row in reader:
                subject = row.get("Subject", "N/A")
                clue_value = 0
                category = subject
                if "." in subject:
                    parts = subject.split(".", 1)
                    if parts[0].isdigit():
                        clue_value = int(parts[0])
                        category = parts[1].strip()

                metadata = {
                    "number": row.get("Number", "N/A"),
                }
                questions.append(
                    Question(
                        question=row.get("Question", "N/A"),
                        answer=row.get("Answer", "N/A"),
                        category=category,
                        clue_value=clue_value,
                        data_source="Knowledge Bowl",
                        metadata=metadata,
                    )
                )
    except FileNotFoundError:
        print(f"Error: The file at {file_path} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

    return questions


def get_random_question(questions: list[Question]) -> Question:
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


if __name__ == "__main__":
    # Example usage
    import os
    from cfg.main import ConfigReader

    config = ConfigReader(
        os.path.join(os.path.dirname(__file__), "..", "cfg", "main.cfg")
    )
    questions = read_jeopardy_questions(config.get("JEOPARDY_LOCAL_PATH"))
    if questions:
        random_question = get_random_question(questions)
        print(random_question)
    else:
        print("No questions found.")
