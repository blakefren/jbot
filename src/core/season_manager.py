"""
SeasonManager - Handles season lifecycle and management.

This manager orchestrates the monthly season system, including:
- Creating and transitioning between seasons
- Calculating season-based statistics
- Finalizing season results and awarding trophies
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional
import calendar

from src.core.data_manager import DataManager
from src.core.season import Season, SeasonScore
from src.cfg.main import ConfigReader


class SeasonManager:
    """Manages the season lifecycle and operations."""

    def __init__(self, data_manager: DataManager, config: ConfigReader):
        """
        Initialize the SeasonManager.

        Args:
            data_manager: DataManager instance for database operations
            config: ConfigReader instance for configuration
        """
        self.data_manager = data_manager
        self.config = config
        self.enabled = config.is_seasons_enabled()
        self.logger = logging.getLogger(__name__)

    def is_enabled(self) -> bool:
        """Check if seasons feature is enabled."""
        return self.enabled

    def get_or_create_current_season(self) -> Optional[Season]:
        """
        Get the current active season, or create one if needed.

        Returns:
            Current Season object, or None if seasons are disabled
        """
        if not self.enabled:
            return None

        current_season = self.data_manager.get_current_season()

        if current_season:
            # Check if we need to transition to a new season
            today = date.today()
            if today > current_season.end_date:
                self.logger.info(
                    f"Current season {current_season.season_name} has ended. Creating new season."
                )
                current_season = self._create_new_season(today)
        else:
            # No active season exists - create one
            self.logger.info("No active season found. Creating new season.")
            current_season = self._create_new_season(date.today())

        return current_season

    def check_season_transition(self, current_date: date = None) -> bool:
        """
        Check if we need to transition to a new season.

        Args:
            current_date: Date to check (defaults to today)

        Returns:
            True if a transition occurred, False otherwise
        """
        if not self.enabled:
            return False

        if current_date is None:
            current_date = date.today()

        current_season = self.data_manager.get_current_season()

        if not current_season:
            # No season exists - create one
            self._create_new_season(current_date)
            return True

        if current_date > current_season.end_date:
            # Season has ended - finalize and create new one
            self.logger.info(
                f"Season {current_season.season_name} ended on {current_season.end_date}"
            )
            self.finalize_season(current_season.season_id)
            self._create_new_season(current_date)
            return True

        return False

    def _create_new_season(self, start_date: date) -> Season:
        """
        Create a new season based on configuration.

        Args:
            start_date: The date to start the season from

        Returns:
            The newly created Season object
        """
        mode = self.config.get_season_mode()

        if mode == "calendar":
            # Calendar mode: monthly seasons
            season_name, start_str, end_str = self._calculate_calendar_season(
                start_date
            )
        else:
            # Rolling mode: fixed N-day periods
            duration = self.config.get_season_duration_days()
            season_name, start_str, end_str = self._calculate_rolling_season(
                start_date, duration
            )

        season_id = self.data_manager.create_season(season_name, start_str, end_str)
        self.logger.info(
            f"Created new season: {season_name} ({start_str} to {end_str})"
        )

        # Reset all player season scores to 0
        self._reset_player_season_scores()

        # Create challenge for the season (if enabled)
        try:
            from src.core.challenge_manager import ChallengeManager

            challenge_mgr = ChallengeManager(self.data_manager, self.config)
            challenge_mgr.create_season_challenge(season_id)
        except Exception as e:
            self.logger.warning(f"Could not create season challenge: {e}")

        return self.data_manager.get_season_by_id(season_id)

    def _calculate_calendar_season(self, ref_date: date) -> tuple[str, str, str]:
        """
        Calculate season dates for calendar month mode.

        Args:
            ref_date: Reference date (typically today)

        Returns:
            Tuple of (season_name, start_date_str, end_date_str)
        """
        # Use the month containing ref_date
        year = ref_date.year
        month = ref_date.month

        # First day of month
        start_date = date(year, month, 1)

        # Last day of month
        _, last_day = calendar.monthrange(year, month)
        end_date = date(year, month, last_day)

        season_name = start_date.strftime("%B %Y")  # e.g., "January 2026"

        return season_name, start_date.isoformat(), end_date.isoformat()

    def _calculate_rolling_season(
        self, start_date: date, duration_days: int
    ) -> tuple[str, str, str]:
        """
        Calculate season dates for rolling N-day mode.

        Args:
            start_date: Date to start the season
            duration_days: Length of season in days

        Returns:
            Tuple of (season_name, start_date_str, end_date_str)
        """
        end_date = start_date + timedelta(days=duration_days - 1)

        season_name = (
            f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
        )

        return season_name, start_date.isoformat(), end_date.isoformat()

    def _reset_player_season_scores(self):
        """Reset all players' season_score and answer_streak to 0."""
        self.logger.info("Resetting player season scores and streaks")
        self.data_manager.reset_all_player_season_scores()

    def finalize_season(self, season_id: int):
        """
        Finalize a season by calculating rankings and awarding trophies.

        Args:
            season_id: ID of the season to finalize
        """
        season = self.data_manager.get_season_by_id(season_id)
        if not season:
            self.logger.error(f"Cannot finalize season {season_id} - not found")
            return

        self.logger.info(f"Finalizing season: {season.season_name}")

        # Calculate rankings and award trophies
        self.data_manager.finalize_season_rankings(season_id)

        # Mark season as inactive
        self.data_manager.end_season(season_id)

        self.logger.info(f"Season {season.season_name} finalized")

    def get_season_leaderboard(
        self, season_id: Optional[int] = None, limit: int = 10
    ) -> list[tuple[SeasonScore, str]]:
        """
        Get the leaderboard for a season.

        Args:
            season_id: Season ID (defaults to current season)
            limit: Number of top players to return

        Returns:
            List of tuples (SeasonScore, player_name)
        """
        if season_id is None:
            current_season = self.get_or_create_current_season()
            if not current_season:
                return []
            season_id = current_season.season_id

        scores = self.data_manager.get_season_scores(season_id, limit)

        # Enrich with player names
        leaderboard = []
        for score in scores:
            player = self.data_manager.get_player(score.player_id)
            player_name = player.name if player else f"Unknown ({score.player_id})"
            leaderboard.append((score, player_name))

        return leaderboard

    def get_all_time_leaderboard(self, limit: int = 10) -> list[tuple[dict, str]]:
        """
        Get the all-time leaderboard based on lifetime scores.

        Args:
            limit: Number of top players to return

        Returns:
            List of tuples (player_dict, player_name) sorted by lifetime score
        """
        players = self.data_manager.get_all_players()
        sorted_players = sorted(players.values(), key=lambda p: p.score, reverse=True)[
            :limit
        ]

        leaderboard = []
        for player in sorted_players:
            player_dict = {
                "player_id": player.id,
                "score": player.score,
                "lifetime_questions": player.lifetime_questions,
                "lifetime_correct": player.lifetime_correct,
                "lifetime_first_answers": player.lifetime_first_answers,
                "lifetime_best_streak": player.lifetime_best_streak,
            }
            leaderboard.append((player_dict, player.name))

        return leaderboard

    def initialize_player_for_season(self, player_id: str, season_id: int):
        """
        Ensure a player has a season_scores record for the given season.

        Args:
            player_id: Player's discord ID
            season_id: Season ID
        """
        self.data_manager.initialize_player_season_score(player_id, season_id)

    def get_days_until_season_end(self, season: Season) -> int:
        """
        Calculate days remaining in the season.

        Args:
            season: Season object

        Returns:
            Number of days until season ends (inclusive)
        """
        today = date.today()
        days_remaining = (season.end_date - today).days
        return max(0, days_remaining)

    def get_season_progress(self, season: Season) -> tuple[int, int]:
        """
        Get the current day and total days of the season.

        Args:
            season: Season object

        Returns:
            Tuple of (current_day, total_days)
        """
        today = date.today()
        total_days = (season.end_date - season.start_date).days + 1
        current_day = (today - season.start_date).days + 1

        # Clamp current_day to valid range
        current_day = max(1, min(current_day, total_days))

        return current_day, total_days

    def should_send_season_reminder(self, season: Season) -> bool:
        """
        Check if we should send a season ending reminder.

        Args:
            season: Current season

        Returns:
            True if reminder should be sent
        """
        if not self.config.get_season_announce_end():
            return False

        days_remaining = self.get_days_until_season_end(season)
        reminder_threshold = self.config.get_season_reminder_days()

        return days_remaining == reminder_threshold

    def get_season_summary(self, season_id: int) -> dict:
        """
        Get a comprehensive summary of a season.

        Args:
            season_id: Season ID

        Returns:
            Dict with season stats
        """
        season = self.data_manager.get_season_by_id(season_id)
        if not season:
            return {}

        top_players = self.get_season_leaderboard(season_id, limit=10)
        challenge = self.data_manager.get_season_challenge(season_id)

        return {
            "season": season,
            "leaderboard": top_players,
            "challenge": challenge,
            "total_players": len(
                self.data_manager.get_season_scores(season_id, limit=1000)
            ),
        }
