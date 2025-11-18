class Player:
    """
    Represents a player in the trivia game.
    Encapsulates all fields from the players table and provides methods for player operations.
    """

    def __init__(
        self,
        id: str,
        name: str,
        score: int = 0,
        answer_streak: int = 0,
        active_shield: bool = False,
    ):
        if not isinstance(id, str):
            raise TypeError(f"Player ID must be a string, but got {type(id)}")
        self.id = id  # Discord ID
        self.name = name
        self.score = score
        self.answer_streak = answer_streak
        self.active_shield = active_shield

    def update_score(self, amount: int):
        self.score += amount

    def set_name(self, name: str):
        self.name = name

    def increment_streak(self):
        self.answer_streak += 1

    def reset_streak(self):
        self.answer_streak = 0

    def activate_shield(self):
        self.active_shield = True

    def deactivate_shield(self):
        self.active_shield = False

    def to_dict(self):
        """
        Returns a dictionary representation for database operations.
        """
        return {
            "id": self.id,
            "name": self.name,
            "score": self.score,
            "answer_streak": self.answer_streak,
            "active_shield": self.active_shield,
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data["id"],
            name=data["name"],
            score=data.get("score", 0),
            answer_streak=data.get("answer_streak", 0),
            active_shield=bool(data.get("active_shield", False)),
        )
