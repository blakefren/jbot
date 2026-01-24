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
        path = config.get_dataset_path("jeopardy")
        score_sub = config.get("JBOT_FINAL_JEOPARDY_SCORE_SUB")
        return read_jeopardy_questions(path, score_sub, allowed_clue_values=[100, 200])
    elif dataset == "knowledge_bowl":
        path = config.get_dataset_path("knowledge_bowl")
        return read_knowledge_bowl_questions(path)
    elif dataset == "riddles_small":
        path = config.get_dataset_path("riddles_small")
        return read_riddle_questions(path)
    elif dataset == "riddles_with_hints":
        path = config.get_dataset_path("riddles_with_hints")
        return read_riddle_with_hints_questions(path)
    elif dataset == "5th_grader":
        path = config.get_dataset_path("5th_grader")
        return read_simple_questions(path, "Are You Smarter Than a Fifth Grader")
    elif dataset == "general_trivia":
        path = config.get_dataset_path("general_trivia")
        return read_general_trivia_questions(path)
    elif dataset == "millionaire_easy":
        path = config.get_dataset_path("millionaire_easy")
        return read_simple_questions(path, "Millionaire (Easy)")
    elif dataset == "millionaire_hard":
        path = config.get_dataset_path("millionaire_hard")
        return read_simple_questions(path, "Millionaire (Hard)")
    else:
        logging.error(f"Unknown dataset: {dataset}")
        return []
