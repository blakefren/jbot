import os
import sys

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

from src.core.data_manager import DataManager
from src.core.player import Player


class PlayerManager:
    def __init__(self, data_manager: DataManager):
        self.data_manager = data_manager

    def _normalize_id(self, discord_id) -> str:
        """Normalize IDs to string keys to avoid int/str mismatches."""
        return str(discord_id) if discord_id is not None else ""

    def get_player(self, discord_id: str) -> Player | None:
        return self.data_manager.get_player(self._normalize_id(discord_id))

    def get_all_players(self) -> dict:
        return self.data_manager.get_all_players()

    def update_score(self, player_id: str, amount: int):
        """
        Updates a player's score and season score by a given amount.
        """
        pid = self._normalize_id(player_id)
        self.data_manager.adjust_player_score(pid, amount)
        self.adjust_season_score(pid, amount)

    def set_name(self, player_id: str, name: str):
        """Updates a player's display name and persists it."""
        pid = self._normalize_id(player_id)
        player = self.data_manager.get_player(pid)
        if player:
            self.data_manager.update_player_name(pid, name)
        else:
            self.data_manager.create_player(pid, name)

    def increment_streak(self, player_id: str, player_name: str | None = None):
        """Increments a player's answer streak and syncs season streak."""
        pid = self._normalize_id(player_id)
        player = self.data_manager.get_player(pid)
        if not player:
            self.data_manager.create_player(pid, player_name or pid)
        self.data_manager.increment_streak(pid)
        new_streak = (player.answer_streak if player else 0) + 1
        self._set_season_streak(pid, new_streak)

    def reset_streak(self, player_id: str):
        """Resets a player's answer streak to zero and syncs season streak."""
        pid = self._normalize_id(player_id)
        self.data_manager.reset_streak(pid)
        self._set_season_streak(pid, 0)

    def reset_unanswered_streaks(self, daily_question_id: int):
        """Resets streaks for all players who didn't answer correctly today."""
        if daily_question_id:
            self.data_manager.reset_unanswered_streaks(daily_question_id)
            current_season = self.data_manager.get_current_season()
            if current_season:
                self.data_manager.reset_unanswered_season_streaks(
                    daily_question_id, current_season.season_id
                )

    def set_streak(self, player_id: str, streak: int):
        """Sets a player's answer streak to a specific value and syncs season streak."""
        pid = self._normalize_id(player_id)
        self.data_manager.set_streak(pid, streak)
        self._set_season_streak(pid, streak)

    def adjust_season_score(self, player_id: str, amount: int):
        """Adjusts a player's season score, if an active season exists."""
        pid = self._normalize_id(player_id)
        current_season = self.data_manager.get_current_season()
        if not current_season:
            return
        self.data_manager.increment_lifetime_stat(pid, "season_score", amount)
        self.data_manager.increment_season_stat(
            pid, current_season.season_id, "points", amount
        )

    def _set_season_streak(self, player_id: str, streak: int):
        """Sync season current_streak (and best_streak if higher)."""
        current_season = self.data_manager.get_current_season()
        if not current_season:
            return
        sid = current_season.season_id
        self.data_manager.initialize_player_season_score(player_id, sid)
        updates = {"current_streak": streak}
        existing = self.data_manager.get_player_season_score(player_id, sid)
        if existing is None or streak > existing.best_streak:
            updates["best_streak"] = streak
        self.data_manager.update_season_score(player_id, sid, **updates)

    # TODO: Implement player creation and refund logic from admin cog
    def get_or_create_player(self, player_id: str, player_name: str) -> Player:
        pid = self._normalize_id(player_id)
        player = self.data_manager.get_player(pid)
        if player is None:
            self.data_manager.create_player(pid, player_name)
            player = self.data_manager.get_player(pid)
        else:
            # Optionally update name if changed
            if player_name and player.name != player_name:
                self.data_manager.update_player_name(pid, player_name)
                player.name = player_name
        return player
