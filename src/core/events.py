from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class GameEvent:
    timestamp: datetime
    user_id: str
    event_sequence: int | None = field(default=None, kw_only=True)


@dataclass
class GuessEvent(GameEvent):
    guess_text: str


@dataclass
class PowerUpEvent(GameEvent):
    powerup_type: str
    target_user_id: str | None = None


class PowerUpOutcome(str):
    """String-compatible jinx/steal result with presentation metadata."""

    def __new__(cls, message: str, public: bool = False):
        outcome = super().__new__(cls, message)
        outcome.public = public
        return outcome


class RestOutcome(tuple):
    """Tuple-compatible rest result with named presentation fields."""

    def __new__(cls, public_message: str, private_message: str):
        outcome = super().__new__(cls, (public_message, private_message))
        outcome.public_message = public_message
        outcome.private_message = private_message
        return outcome


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
    guess_number: int | None = None
