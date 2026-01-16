from dataclasses import dataclass, field
from typing import Optional, Dict


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
    bonuses: Dict[str, int] = field(default_factory=dict)

    # Power-up: Wager
    wager: int = 0

    # Power-up: Defense
    shield_active: bool = False
    shield_used: bool = False
    shield_broken: bool = False

    # Power-up: Attack (Incoming)
    jinxed_by: Optional[str] = None  # User ID
    steal_attempt_by: Optional[str] = None  # User ID

    # Power-up: Attack (Outgoing)
    silenced: bool = False  # Result of jinxing
    stealing_from: Optional[str] = None  # User ID

    # Power-up: Coop
    team_partner: Optional[str] = None  # User ID
    team_success: bool = False

    @property
    def earned_today(self) -> int:
        """Alias for score_earned to match PowerUpManager naming conventions."""
        return self.score_earned

    @property
    def bonuses_today(self) -> Dict[str, int]:
        """Alias for bonuses."""
        return self.bonuses

    @bonuses_today.setter
    def bonuses_today(self, value: Dict[str, int]):
        self.bonuses = value

    @property
    def powerup_used_today(self) -> bool:
        """
        Determines if a powerup was used today based on state flags.
        """
        return (
            self.wager > 0
            or self.shield_active
            or self.silenced
            or self.team_partner is not None
            or self.stealing_from is not None
        )
