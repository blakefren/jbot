import os
import sys
from typing import Optional

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

from db.database import Database
from src.core.data_manager import DataManager
from src.core.player import Player


class PlayerManager:
    def __init__(self, data_manager: DataManager):
        self.data_manager = data_manager
        self.players = self.data_manager.load_players()

    def _normalize_id(self, discord_id) -> str:
        """Normalize IDs to string keys to avoid int/str mismatches."""
        return str(discord_id) if discord_id is not None else ""

    def get_player(self, discord_id: str) -> Optional[Player]:
        return self.players.get(self._normalize_id(discord_id))

    def get_all_players(self) -> dict:
        return self.players

    def save_players(self):
        """
        Writes the current player data back to the database.
        """
        self.data_manager.save_players(self.players)

    def update_score(self, player_id: str, amount: int):
        """
        Updates a player's score by a given amount.
        """
        player = self.get_player(player_id)
        if player:
            player.score += amount
            self.save_players()

    def set_name(self, player_id: str, name: str):
        """Updates a player's display name and persists it."""
        pid = self._normalize_id(player_id)
        player = self.players.get(pid)
        if player:
            player.name = name
            self.save_players()
        else:
            # create if missing
            self.players[pid] = Player(id=pid, name=name)
            self.save_players()

    def increment_streak(self, player_id: str, player_name: Optional[str] = None):
        """Increments a player's answer streak and immediately persists to DB."""
        pid = self._normalize_id(player_id)
        player = self.players.get(pid)
        if not player:
            # Create player if not in memory yet
            player = Player(id=pid, name=player_name or pid)
            self.players[pid] = player
        player.answer_streak += 1
        self.save_players()

    def reset_streak(self, player_id: str):
        """Resets a player's answer streak to zero and persists."""
        player = self.get_player(player_id)
        if player and player.answer_streak != 0:
            player.answer_streak = 0
            self.save_players()

    def activate_shield(self, player_id: str):
        """Activates a player's shield and persists."""
        player = self.get_player(player_id)
        if player and not player.active_shield:
            player.active_shield = True
            self.save_players()

    def deactivate_shield(self, player_id: str):
        """Deactivates a player's shield and persists."""
        player = self.get_player(player_id)
        if player and player.active_shield:
            player.active_shield = False
            self.save_players()

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
        player = self.get_player(pid)
        if player is None:
            player = Player(id=pid, name=player_name)
            self.players[pid] = player
            self.save_players()
        else:
            # Optionally update name if changed
            if player_name and player.name != player_name:
                player.name = player_name
                self.save_players()
        return player

    def refund_score(self, player_id: str, amount: int):
        """
        Refunds a player's score by a given amount and saves it to the database.
        """
        player = self.get_player(player_id)
        if player:
            player.score += amount
            self.save_players()

    def reload_players(self):
        """
        Reloads player data from the database.
        """
        self.players = self.data_manager.load_players()
