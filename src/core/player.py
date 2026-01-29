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
    active_shield: bool = False
    # Lifetime statistics
    lifetime_questions: int = 0
    lifetime_correct: int = 0
    lifetime_first_answers: int = 0
    lifetime_best_streak: int = 0

    def to_dict(self) -> dict:
        """Dictionary representation for database operations."""
        return {
            "id": self.id,
            "name": self.name,
            "score": self.score,
            "season_score": self.season_score,
            "answer_streak": self.answer_streak,
            "active_shield": self.active_shield,
            "lifetime_questions": self.lifetime_questions,
            "lifetime_correct": self.lifetime_correct,
            "lifetime_first_answers": self.lifetime_first_answers,
            "lifetime_best_streak": self.lifetime_best_streak,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Player":
        return cls(
            id=str(data["id"]),
            name=data["name"],
            score=int(data.get("score", 0)),
            season_score=int(data.get("season_score", 0)),
            answer_streak=int(data.get("answer_streak", 0)),
            active_shield=bool(data.get("active_shield", False)),
            lifetime_questions=int(data.get("lifetime_questions", 0)),
            lifetime_correct=int(data.get("lifetime_correct", 0)),
            lifetime_first_answers=int(data.get("lifetime_first_answers", 0)),
            lifetime_best_streak=int(data.get("lifetime_best_streak", 0)),
        )
