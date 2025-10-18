import os
import sys

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

from db.database import Database

from src.core.data_manager import DataManager

class PlayerManager:
    def __init__(self, db: Database):
        self.data_manager = DataManager(db)
        self.players = self.data_manager.load_players()

    def get_player(self, discord_id: str):
        return self.players.get(discord_id)

    def get_all_players(self):
        return self.players

    def save_players(self):
        """
        Writes the current player data back to the database.
        """
        self.data_manager.save_players(self.players)

    # TODO: Implement score update logic from GameRunner
    def update_score(self, player_id: str, amount: int):
        """
        Updates a player's score by a given amount.
        """
        pass

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
    def get_or_create_player(self, player_id: str, player_name: str):
        pass

    def refund_score(self, player_id: str, amount: int):
        """
        Refunds a player's score by a given amount and saves it to the database.
        """
        if player_id in self.players:
            self.players[player_id]["score"] += amount
            self.save_players()


# TODO: Migrate this function to DataManager
def read_players_into_dict():
    db = Database()
    manager = PlayerManager(db)
    return manager.get_all_players()
