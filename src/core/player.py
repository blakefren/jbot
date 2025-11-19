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
    active_shield: bool = False

    def to_dict(self) -> dict:
        """Dictionary representation for database operations."""
        return {
            "id": self.id,
            "name": self.name,
            "score": self.score,
            "answer_streak": self.answer_streak,
            "active_shield": self.active_shield,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Player":
        return cls(
            id=str(data["id"]),
            name=data["name"],
            score=int(data.get("score", 0)),
            answer_streak=int(data.get("answer_streak", 0)),
            active_shield=bool(data.get("active_shield", False)),
        )
