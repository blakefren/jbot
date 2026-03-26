from dataclasses import dataclass, field


@dataclass
class DailyPlayerState:
    """
    Represents the transient state of a player for a single day.
    This state is recalculated daily via the DailyGameSimulator or
    managed in-memory by the PowerUpManager.
    """

    # Scoring & Progress
    score_earned: int = 0
    streak_delta: int = 0
    is_correct: bool = False
    guesses_count: int = 0
    bonuses: dict[str, int] = field(default_factory=dict)

    # Power-up: Defense / Rest
    is_resting: bool = False

    # Power-up: Attack (Incoming)
    jinxed_by: str | None = None  # User ID
    steal_attempt_by: str | None = None  # User ID

    # Power-up: Attack (Outgoing)
    silenced: bool = False  # Result of jinxing
    stealing_from: str | None = None  # User ID
    steal_ratio: float = (
        1.0  # Fraction of stealable bonuses the thief receives (≤1.0 when partial)
    )

    @property
    def powerup_used_today(self) -> bool:
        """
        Determines if a powerup was used today based on state flags.
        """
        return self.is_resting or self.silenced or self.stealing_from is not None
