import csv
from readers.question import Question

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
                question_text = row["QUESTIONS"]
                answer_text = row["ANSWERS"]
                question = Question(
                    question=question_text,
                    answer=answer_text,
                    category="Riddle",
                    clue_value=100, # Default value for riddles
                    data_source="Riddles (small)",
                )
                questions.append(question)
    except FileNotFoundError:
        print(f"Error: The file at {file_path} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")
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
                question_text = row["Riddle"]
                answer_text = row["Answer"]
                hint_text = row["Hint"]
                question = Question(
                    question=question_text,
                    answer=answer_text,
                    category="Riddle with Hint",
                    clue_value=100,  # Default value for riddles
                    data_source="Riddles with Hints",
                    metadata={"hint": hint_text},
                )
                questions.append(question)
    except FileNotFoundError:
        print(f"Error: The file at {file_path} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")
    return questions
