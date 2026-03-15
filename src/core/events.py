from dataclasses import dataclass
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
