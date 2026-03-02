from dataclasses import dataclass


@dataclass
class Player:
    """
    Represents a player in the trivia game as a plain data structure.
    Contains fields from the players table; all behavior lives in PlayerManager.
    """

    id: str  # Discord ID (stored as string key)
    name: str
    score: int = 0
    answer_streak: int = 0
    pending_rest_multiplier: float = 0.0

    def to_dict(self) -> dict:
        """Dictionary representation for database operations."""
        return {
            "id": self.id,
            "name": self.name,
            "score": self.score,
            "answer_streak": self.answer_streak,
            "pending_rest_multiplier": self.pending_rest_multiplier,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Player":
        return cls(
            id=str(data["id"]),
            name=data["name"],
            score=int(data.get("score", 0)),
            answer_streak=int(data.get("answer_streak", 0)),
            pending_rest_multiplier=float(data.get("pending_rest_multiplier", 0.0)),
        )
