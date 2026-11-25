from dataclasses import dataclass


@dataclass
class Player:
    """
    Represents a player in the trivia game as a plain data structure.
    Contains fields from the players table; all behavior lives in PlayerManager.
    """

    id: str  # Discord ID (stored as string key)
    name: str
    score: int = 0  # Lifetime total score (unchanged for compatibility)
    season_score: int = 0  # Current season score
    answer_streak: int = 0  # Current season streak
    pending_rest_multiplier: float = 0.0
    # Lifetime statistics
    lifetime_questions: int = 0
    lifetime_correct: int = 0
    lifetime_first_answers: int = 0
    lifetime_best_streak: int = 0
