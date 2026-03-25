from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class GameEvent:
    timestamp: datetime
    user_id: str


@dataclass
class GuessEvent(GameEvent):
    guess_text: str
    is_correct: bool = False  # Populated during simulation


@dataclass
class PowerUpEvent(GameEvent):
    powerup_type: str
    target_user_id: str | None = None


@dataclass
class GuessContext:
    """
    Carries all per-guess state through the manager pipeline.
    Managers may mutate `points_earned`, `bonus_values`, and `bonus_messages`.
    """

    player_id: int | str
    player_name: str
    guess: str
    is_correct: bool
    points_earned: int = 0
    bonus_values: dict = field(default_factory=dict)
    bonus_messages: list = field(default_factory=list)
    question_id: int | None = None
