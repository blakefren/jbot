"""
ChallengeManager - Handles monthly season challenges.

This manager orchestrates monthly challenges that provide extra goals
and badges for players during each season.
"""

import logging
import random
from typing import Optional

from src.core.data_manager import DataManager
from src.core.season import SeasonChallenge
from src.cfg.main import ConfigReader

# Challenge pool - predefined challenges that rotate monthly
CHALLENGE_POOL = [
    {
        "name": "Speed Demon",
        "description": "Answer 10 questions before the hint is revealed",
        "emoji": "🤘",
        "criteria": {"before_hint_count": 10},
    },
    {
        "name": "Perfectionist",
        "description": "Achieve a 7-day answer streak",
        "emoji": "👌",
        "criteria": {"streak_threshold": 7},
    },
    {
        "name": "First Blood",
        "description": "Be the first to answer correctly 5 times this season",
        "emoji": "👊",
        "criteria": {"first_answer_count": 5},
    },
    {
        "name": "Marathon Runner",
        "description": "Answer 25 questions this season",
        "emoji": "👉",
        "criteria": {"questions_answered": 25},
    },
    {
        "name": "Ace",
        "description": "Get 15 correct answers this season",
        "emoji": "👆",
        "criteria": {"correct_answers": 15},
    },
    {
        "name": "Sharpshooter",
        "description": "Answer 3 questions correctly on your first try",
        "emoji": "🤞",
        "criteria": {"first_try_correct": 3},
    },
]


class ChallengeManager:
    """Manages monthly season challenges."""

    def __init__(self, data_manager: DataManager, config: ConfigReader):
        """
        Initialize the ChallengeManager.

        Args:
            data_manager: DataManager instance for database operations
            config: ConfigReader instance for configuration
        """
        self.data_manager = data_manager
        self.config = config
        self.logger = logging.getLogger(__name__)

    def create_season_challenge(self, season_id: int) -> Optional[int]:
        """
        Auto-select and create a challenge for a new season.

        Args:
            season_id: The season to create a challenge for

        Returns:
            challenge_id of the created challenge, or None
        """
        # Get the previous season's challenge to avoid repeats
        all_seasons = self.data_manager.get_all_seasons(order_by="start_date DESC")
        previous_challenge_name = None

        if len(all_seasons) > 1:
            previous_season = all_seasons[1]  # Second most recent
            prev_challenge = self.data_manager.get_season_challenge(
                previous_season.season_id
            )
            if prev_challenge:
                previous_challenge_name = prev_challenge.challenge_name

        # Select a challenge that's different from previous
        available_challenges = [
            c for c in CHALLENGE_POOL if c["name"] != previous_challenge_name
        ]

        if not available_challenges:
            # Fallback: use first challenge if all were filtered
            available_challenges = CHALLENGE_POOL

        selected = random.choice(available_challenges)

        # Create the challenge
        challenge_id = self.data_manager.create_season_challenge(
            season_id=season_id,
            challenge_name=selected["name"],
            description=selected["description"],
            badge_emoji=selected["emoji"],
            completion_criteria=selected["criteria"],
        )

        self.logger.info(
            f"Created challenge for season {season_id}: {selected['name']}"
        )
        return challenge_id

    def check_challenge_progress(
        self, player_id: str, season_id: int, challenge: SeasonChallenge
    ) -> tuple[bool, int, int]:
        """
        Check a player's progress toward completing a challenge.

        Args:
            player_id: Player's discord ID
            season_id: Current season ID
            challenge: The SeasonChallenge to check

        Returns:
            Tuple of (is_complete, current_progress, goal)
        """
        season_score = self.data_manager.get_player_season_score(player_id, season_id)
        if not season_score:
            return False, 0, self._get_challenge_goal(challenge)

        criteria = challenge.completion_criteria
        current_progress = 0
        goal = self._get_challenge_goal(challenge)

        # Check different challenge types
        if "before_hint_count" in criteria:
            # Track in challenge_progress JSON
            current_progress = season_score.challenge_progress.get(
                "before_hint_answers", 0
            )
            goal = criteria["before_hint_count"]

        elif "streak_threshold" in criteria:
            current_progress = season_score.best_streak
            goal = criteria["streak_threshold"]

        elif "first_answer_count" in criteria:
            current_progress = season_score.first_answers
            goal = criteria["first_answer_count"]

        elif "questions_answered" in criteria:
            current_progress = season_score.questions_answered
            goal = criteria["questions_answered"]

        elif "correct_answers" in criteria:
            current_progress = season_score.correct_answers
            goal = criteria["correct_answers"]

        elif "first_try_correct" in criteria:
            # Track in challenge_progress JSON
            current_progress = season_score.challenge_progress.get(
                "first_try_correct", 0
            )
            goal = criteria["first_try_correct"]

        is_complete = current_progress >= goal
        return is_complete, current_progress, goal

    def _get_challenge_goal(self, challenge: SeasonChallenge) -> int:
        """Extract the goal value from challenge criteria."""
        criteria = challenge.completion_criteria

        for key in [
            "before_hint_count",
            "streak_threshold",
            "first_answer_count",
            "questions_answered",
            "correct_answers",
            "first_try_correct",
        ]:
            if key in criteria:
                return criteria[key]

        return 0

    def update_challenge_progress(
        self,
        player_id: str,
        season_id: int,
        event_type: str,
        increment: int = 1,
    ):
        """
        Update a player's progress toward challenge completion.

        Args:
            player_id: Player's discord ID
            season_id: Current season ID
            event_type: Type of progress event (e.g., "before_hint_answer")
            increment: Amount to increment by (default 1)
        """
        season_score = self.data_manager.get_player_season_score(player_id, season_id)
        if not season_score:
            self.data_manager.initialize_player_season_score(player_id, season_id)
            season_score = self.data_manager.get_player_season_score(
                player_id, season_id
            )

        # Update challenge_progress JSON
        progress = season_score.challenge_progress.copy()

        if event_type == "before_hint_answer":
            progress["before_hint_answers"] = (
                progress.get("before_hint_answers", 0) + increment
            )
        elif event_type == "first_try_correct":
            progress["first_try_correct"] = (
                progress.get("first_try_correct", 0) + increment
            )

        # Save updated progress
        import json

        self.data_manager.update_season_score(
            player_id, season_id, challenge_progress=json.dumps(progress)
        )

    def get_challenge_display(
        self, player_id: str, season_id: int, challenge: SeasonChallenge
    ) -> str:
        """
        Get a formatted string showing challenge progress.

        Args:
            player_id: Player's discord ID
            season_id: Current season ID
            challenge: The SeasonChallenge

        Returns:
            Formatted string like "⚡ Speed Demon: 3/10 answers before hint"
        """
        is_complete, current, goal = self.check_challenge_progress(
            player_id, season_id, challenge
        )

        status = "✅ Complete!" if is_complete else f"{current}/{goal}"
        return f"{challenge.badge_emoji} {challenge.challenge_name}: {status}"

    def get_all_challenge_completions(
        self, season_id: int, challenge: SeasonChallenge
    ) -> list[str]:
        """
        Get list of all players who completed the challenge.

        Args:
            season_id: Season ID
            challenge: The SeasonChallenge

        Returns:
            List of player IDs who completed the challenge
        """
        all_scores = self.data_manager.get_season_scores(season_id, limit=1000)
        completions = []

        for score in all_scores:
            is_complete, _, _ = self.check_challenge_progress(
                score.player_id, season_id, challenge
            )
            if is_complete:
                completions.append(score.player_id)

        return completions
