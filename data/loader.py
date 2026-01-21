import os
import sys
import logging

# Add the project root to the Python path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from src.cfg.main import ConfigReader
from data.readers.question import Question
from data.readers.tsv import read_jeopardy_questions
from data.readers.csv_reader import (
    read_riddle_questions,
    read_riddle_with_hints_questions,
    read_knowledge_bowl_questions,
    read_simple_questions,
    read_general_trivia_questions,
)


def load_questions(config: ConfigReader) -> list[Question]:
    """
    Reads questions from the dataset specified in the config.
    """
    dataset = config.get("JBOT_QUESTION_DATASET")
    logging.info(f"Reading '{dataset}' questions from file...")

    if dataset == "jeopardy":
        path = os.path.join(PROJECT_ROOT, config.get("JBOT_JEOPARDY_LOCAL_PATH"))
        score_sub = config.get("JBOT_FINAL_JEOPARDY_SCORE_SUB")
        return read_jeopardy_questions(path, score_sub, allowed_clue_values=[100, 200])
    elif dataset == "knowledge_bowl":
        path = os.path.join(PROJECT_ROOT, config.get("JBOT_KNOWLEDGE_BOWL_LOCAL_PATH"))
        return read_knowledge_bowl_questions(path)
    elif dataset == "riddles_small":
        path = os.path.join(PROJECT_ROOT, config.get("JBOT_RIDDLE_SMALL_LOCAL_PATH"))
        return read_riddle_questions(path)
    elif dataset == "riddles_with_hints":
        path = os.path.join(PROJECT_ROOT, config.get("JBOT_RIDDLE_HINTS_LOCAL_PATH"))
        return read_riddle_with_hints_questions(path)
    elif dataset == "5th_grader":
        path = os.path.join(PROJECT_ROOT, config.get("JBOT_5TH_GRADER_LOCAL_PATH"))
        return read_simple_questions(path, "Are You Smarter Than a Fifth Grader")
    elif dataset == "general_trivia":
        path = os.path.join(PROJECT_ROOT, config.get("JBOT_GENERAL_TRIVIA_LOCAL_PATH"))
        return read_general_trivia_questions(path)
    elif dataset == "millionaire_easy":
        path = os.path.join(
            PROJECT_ROOT, config.get("JBOT_MILLIONAIRE_EASY_LOCAL_PATH")
        )
        return read_simple_questions(path, "Millionaire (Easy)")
    elif dataset == "millionaire_hard":
        path = os.path.join(
            PROJECT_ROOT, config.get("JBOT_MILLIONAIRE_HARD_LOCAL_PATH")
        )
        return read_simple_questions(path, "Millionaire (Hard)")
    else:
        logging.error(f"Unknown dataset: {dataset}")
        return []
