"""
Season data models for the monthly competition system.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class Season:
    """Represents a competitive season (typically monthly)."""

    season_id: int
    season_name: str  # e.g., "January 2026"
    start_date: date  # First day of the season
    end_date: date  # Last day of the season
    is_active: bool  # True if this is the current season

    def __str__(self) -> str:
        return f"{self.season_name} ({self.start_date} to {self.end_date})"

    @property
    def is_current(self) -> bool:
        """Check if this season is currently active."""
        return self.is_active

    @classmethod
    def from_db_row(cls, row: dict) -> "Season":
        """Create Season from database row."""
        return cls(
            season_id=row["season_id"],
            season_name=row["season_name"],
            start_date=date.fromisoformat(row["start_date"]),
            end_date=date.fromisoformat(row["end_date"]),
            is_active=bool(row["is_active"]),
        )


@dataclass
class SeasonScore:
    """Represents a player's performance within a specific season."""

    player_id: str
    season_id: int
    points: int = 0
    questions_answered: int = 0
    correct_answers: int = 0
    first_answers: int = 0
    current_streak: int = 0
    best_streak: int = 0
    shields_used: int = 0
    double_points_used: int = 0
    challenge_progress: dict = None  # JSON data for challenge tracking
    final_rank: Optional[int] = None  # Set when season ends
    trophy: Optional[str] = None  # "gold", "silver", "bronze", or None

    def __post_init__(self):
        """Initialize challenge_progress as empty dict if None."""
        if self.challenge_progress is None:
            self.challenge_progress = {}

    @classmethod
    def from_db_row(cls, row: dict) -> "SeasonScore":
        """Create SeasonScore from database row."""
        import json

        return cls(
            player_id=row["player_id"],
            season_id=row["season_id"],
            points=row["points"],
            questions_answered=row["questions_answered"],
            correct_answers=row["correct_answers"],
            first_answers=row["first_answers"],
            current_streak=row["current_streak"],
            best_streak=row["best_streak"],
            shields_used=row["shields_used"],
            double_points_used=row["double_points_used"],
            challenge_progress=(
                json.loads(row["challenge_progress"])
                if row["challenge_progress"]
                else {}
            ),
            final_rank=row["final_rank"],
            trophy=row["trophy"],
        )

    @property
    def trophy_emoji(self) -> str:
        """Get the emoji representation of the trophy."""
        if self.trophy == "gold":
            return "🥇"
        elif self.trophy == "silver":
            return "🥈"
        elif self.trophy == "bronze":
            return "🥉"
        return ""


@dataclass
class SeasonChallenge:
    """Represents a monthly challenge for a season."""

    challenge_id: int
    season_id: int
    challenge_name: str  # e.g., "Speed Demon"
    description: str  # e.g., "Answer 10 questions before hint"
    badge_emoji: str  # e.g., "⚡"
    completion_criteria: dict  # JSON criteria for completion

    @classmethod
    def from_db_row(cls, row: dict) -> "SeasonChallenge":
        """Create SeasonChallenge from database row."""
        import json

        return cls(
            challenge_id=row["challenge_id"],
            season_id=row["season_id"],
            challenge_name=row["challenge_name"],
            description=row["description"],
            badge_emoji=row["badge_emoji"],
            completion_criteria=json.loads(row["completion_criteria"]),
        )

    def __str__(self) -> str:
        return f"{self.badge_emoji} {self.challenge_name}: {self.description}"
