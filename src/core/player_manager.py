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
    def __init__(self, db: Database):
        self.data_manager = DataManager(db)
        self.players = self.data_manager.load_players()

    def get_player(self, discord_id: str) -> Optional[Player]:
        return self.players.get(discord_id)

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
            player.update_score(amount)
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
        player = self.get_player(player_id)
        if player is None:
            player = Player(id=player_id, name=player_name)
            self.players[player_id] = player
            self.save_players()
        else:
            # Optionally update name if changed
            if player.name != player_name:
                player.set_name(player_name)
                self.save_players()
        return player

    def refund_score(self, player_id: str, amount: int):
        """
        Refunds a player's score by a given amount and saves it to the database.
        """
        player = self.get_player(player_id)
        if player:
            player.update_score(amount)
            self.save_players()

    def reload_players(self):
        """
        Reloads player data from the database.
        """
        self.players = self.data_manager.load_players()
