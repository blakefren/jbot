import os
import sys

# Add the project root to the Python path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from src.cfg.main import ConfigReader
from data.readers.question import Question
from data.readers.tsv import (
    read_jeopardy_questions,
    read_knowledge_bowl_questions,
)
from data.readers.csv_reader import (
    read_riddle_questions,
    read_riddle_with_hints_questions,
)


def load_questions(config: ConfigReader) -> list[Question]:
    """
    Reads questions from the dataset specified in the config.
    """
    dataset = config.get("JBOT_QUESTION_DATASET")
    print(f"Reading '{dataset}' questions from file...")

    if dataset == "jeopardy":
        path = os.path.join(PROJECT_ROOT, config.get("JBOT_JEOPARDY_LOCAL_PATH"))
        score_sub = config.get("JBOT_FINAL_JEOPARDY_SCORE_SUB")
        return read_jeopardy_questions(path, score_sub)
    elif dataset == "knowledge_bowl":
        path = os.path.join(PROJECT_ROOT, config.get("JBOT_KNOWLEDGE_BOWL_LOCAL_PATH"))
        return read_knowledge_bowl_questions(path)
    elif dataset == "riddles_small":
        path = os.path.join(PROJECT_ROOT, config.get("JBOT_RIDDLE_SMALL_LOCAL_PATH"))
        return read_riddle_questions(path)
    elif dataset == "riddles_with_hints":
        path = os.path.join(PROJECT_ROOT, config.get("JBOT_RIDDLE_HINTS_LOCAL_PATH"))
        return read_riddle_with_hints_questions(path)
    else:
        print(f"Unknown dataset: {dataset}")
        return []
