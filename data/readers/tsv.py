import csv
import random
import logging
from collections import defaultdict

from data.readers.question import Question


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
    file_path: str,
    difficulty: str = "easy",
    final_jeopardy_score: int = 300,
) -> list[Question]:
    """
    Reads a TSV file of Jeopardy! questions and returns a list of Question objects
    filtered by difficulty level based on question position within each category.

    Args:
        file_path: Path to the TSV file containing Jeopardy! questions.
        difficulty: Difficulty level - "easy", "medium", or "hard".
                   - "easy": Questions at positions 1-2 of 5 in each category
                   - "medium": Questions at positions 3-4 of 5 in each category
                   - "hard": Questions at position 5 of 5 + Final Jeopardy
        final_jeopardy_score: Point value to assign to Final Jeopardy questions (default 300).

    Returns:
        List of Question objects filtered by the specified difficulty level.
    """
    # Validate difficulty parameter
    difficulty = difficulty.lower()
    if difficulty not in ("easy", "medium", "hard"):
        logging.error(
            f"Invalid difficulty '{difficulty}'. Defaulting to 'easy'. "
            f"Valid options: easy, medium, hard"
        )
        difficulty = "easy"

    # Step 1: Read all questions and group by (air_date, round, category)
    all_rows = []
    try:
        with open(file_path, "r", encoding="utf-8") as tsvfile:
            reader = csv.DictReader(tsvfile, delimiter="\t")
            for row in reader:
                all_rows.append(row)
    except FileNotFoundError:
        logging.error(f"The file at {file_path} was not found.")
        return []
    except Exception as e:
        logging.error(f"An error occurred while reading Jeopardy questions: {e}")
        return []

    # Step 2: Group questions by (air_date, round, category)
    grouped_questions = defaultdict(list)
    for row in all_rows:
        air_date = row.get("air_date", "N/A")
        round_name = row.get("round", "N/A")
        category = row.get("category", "N/A")

        # Skip if missing critical fields
        if air_date == "N/A" or category == "N/A":
            continue

        key = (air_date, round_name, category)
        grouped_questions[key].append(row)

    # Step 3: Process each group to assign positions and filter by difficulty
    filtered_questions = []

    for (air_date, round_name, category), rows in grouped_questions.items():
        # Handle Final Jeopardy separately
        if round_name == "Final Jeopardy!":
            if difficulty == "hard":
                for row in rows:
                    metadata = {
                        "round": round_name,
                        "air_date": air_date,
                        "daily_double": row.get("daily_double_value", 0),
                        "original_clue_value": row.get("clue_value", "N/A"),
                    }
                    filtered_questions.append(
                        Question(
                            question=row.get("answer", "N/A"),
                            answer=row.get("question", "N/A"),
                            category=row.get("category", "N/A"),
                            clue_value=final_jeopardy_score,
                            data_source="Jeopardy!",
                            metadata=metadata,
                        )
                    )
            continue

        # Sort questions by clue value to determine position
        sorted_rows = sorted(rows, key=lambda r: parse_value(r.get("clue_value", "0")))

        # Assign positions and filter based on difficulty
        for position, row in enumerate(sorted_rows, start=1):
            include_question = False

            if difficulty == "easy" and position in (1, 2):
                include_question = True
                normalized_points = 100
            elif difficulty == "medium" and position in (3, 4):
                include_question = True
                normalized_points = 200
            elif difficulty == "hard" and position == 5:
                include_question = True
                normalized_points = 300

            if include_question:
                metadata = {
                    "round": round_name,
                    "air_date": air_date,
                    "daily_double": row.get("daily_double_value", 0),
                    "original_clue_value": row.get("clue_value", "N/A"),
                    "position": position,
                }
                filtered_questions.append(
                    Question(
                        question=row.get("answer", "N/A"),
                        answer=row.get("question", "N/A"),
                        category=row.get("category", "N/A"),
                        clue_value=normalized_points,
                        data_source="Jeopardy!",
                        metadata=metadata,
                    )
                )

    logging.info(
        f"Loaded {len(filtered_questions)} Jeopardy! questions with difficulty '{difficulty}'"
    )
    return filtered_questions


def read_knowledge_bowl_questions(file_path: str) -> list[Question]:
    """
    Reads a TSV file of Knowledge Bowl questions and returns a list of Questions.
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

                questions.append(
                    Question(
                        question=row.get("Question", "N/A"),
                        answer=row.get("Answer", "N/A"),
                        category=category,
                        clue_value=clue_value,
                        data_source="Knowledge Bowl",
                        metadata={"number": row.get("Number", "N/A")},
                    )
                )
    except FileNotFoundError:
        logging.error(f"The file at {file_path} was not found.")
    except Exception as e:
        logging.error(f"An error occurred while reading Knowledge Bowl questions: {e}")

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


if __name__ == "__main__":  # pragma: no cover
    # Example usage for testing the question readers
    import os

    # Add the project root to the Python path to allow imports from `src`
    import sys

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    sys.path.insert(0, project_root)
    from src.cfg.main import ConfigReader

    # Create a dummy config for testing
    config_path = os.path.join(os.path.dirname(__file__), "..", "cfg", "main.cfg")
    if os.path.exists(config_path):
        config = ConfigReader()

        # Test Jeopardy reader
        jeopardy_path = config.get("JEOPARDY_LOCAL_PATH")
        if jeopardy_path and jeopardy_path != "todo":
            jeopardy_questions = read_jeopardy_questions(jeopardy_path)
            if jeopardy_questions:
                logging.info("--- Random Jeopardy Question ---")
                logging.info(get_random_question(jeopardy_questions))
            else:
                logging.warning(
                    "No Jeopardy questions found or file path is a placeholder."
                )
        else:
            logging.warning("Jeopardy file path not configured or is 'todo'.")

        # Test Knowledge Bowl reader
        kb_path = config.get("KNOWLEDGE_BOWL_LOCAL_PATH")
        if kb_path and kb_path != "todo":
            kb_questions = read_knowledge_bowl_questions(kb_path)
            if kb_questions:
                logging.info("--- Random Knowledge Bowl Question ---")
                logging.info(get_random_question(kb_questions))
            else:
                logging.warning(
                    "No Knowledge Bowl questions found or file path is a placeholder."
                )
        else:
            logging.warning("Knowledge Bowl file path not configured or is 'todo'.")
    else:
        logging.warning(
            f"Config file not found at {config_path}, skipping example usage."
        )
