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
        Updates a player's score by a given amount.
        """
        self.data_manager.adjust_player_score(self._normalize_id(player_id), amount)

    def set_name(self, player_id: str, name: str):
        """Updates a player's display name and persists it."""
        pid = self._normalize_id(player_id)
        player = self.data_manager.get_player(pid)
        if player:
            self.data_manager.update_player_name(pid, name)
        else:
            self.data_manager.create_player(pid, name)

    def increment_streak(self, player_id: str, player_name: str | None = None):
        """Increments a player's answer streak and immediately persists to DB."""
        pid = self._normalize_id(player_id)
        player = self.data_manager.get_player(pid)
        if not player:
            self.data_manager.create_player(pid, player_name or pid)
        self.data_manager.increment_streak(pid)

    def reset_streak(self, player_id: str):
        """Resets a player's answer streak to zero and persists."""
        self.data_manager.reset_streak(self._normalize_id(player_id))

    def reset_unanswered_streaks(self, daily_question_id: int):
        """Resets streaks for all players who didn't answer correctly today."""
        if daily_question_id:
            self.data_manager.reset_unanswered_streaks(daily_question_id)

    def set_streak(self, player_id: str, streak: int):
        """Sets a player's answer streak to a specific value and persists."""
        self.data_manager.set_streak(self._normalize_id(player_id), streak)

    def activate_shield(self, player_id: str):
        """Activates a player's shield and persists."""
        self.data_manager.set_shield(self._normalize_id(player_id), True)

    def deactivate_shield(self, player_id: str):
        """Deactivates a player's shield and persists."""
        self.data_manager.set_shield(self._normalize_id(player_id), False)

    # TODO: Implement powerup logic from powerup manager
    def reinforce(self, player1_id: str, player2_id: str):
        pass

    def resolve_reinforce(self, player_id: str, correct: bool):
        pass

    def steal(self, thief_id: str, target_id: str):
        pass

    def disrupt(self, attacker_id: str, target_id: str):
        pass

    def use_shield(self, player_id: str):
        pass

    def place_wager(self, player_id: str, amount: int):
        pass

    def resolve_wager(self, player_id: str, correct: bool):
        pass

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
