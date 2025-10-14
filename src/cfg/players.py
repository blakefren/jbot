import os
import sys

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

from db.database import Database


class PlayerManager:
    def __init__(self, db: Database):
        self.db = db
        self.players = self._load_players()

    # TODO: Migrate _load_players to DataManager
    def _load_players(self):
        """
        Reads the players table and returns a dictionary of player data.
        """
        players = {}
        query = "SELECT id, name, score, answer_streak, active_shield FROM players"
        player_records = self.db.execute_query(query)
        for record in player_records:
            discord_id = record["id"]
            players[discord_id] = {
                "name": record["name"],
                "score": record["score"],
                "answer_streak": record["answer_streak"],
                "active_shield": bool(record["active_shield"]),
            }
        return players

    def get_player(self, discord_id: str):
        return self.players.get(discord_id)

    def get_all_players(self):
        return self.players

    # TODO: Migrate save_players to DataManager
    def save_players(self):
        """
        Writes the current player data back to the database.
        """
        for discord_id, data in self.players.items():
            query = """
                INSERT INTO players (id, name, score, answer_streak, active_shield)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    score = excluded.score,
                    answer_streak = excluded.answer_streak,
                    active_shield = excluded.active_shield;
            """
            params = (
                discord_id,
                data["name"],
                data["score"],
                data["answer_streak"],
                data["active_shield"],
            )
            self.db.execute_update(query, params)

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
        pass


# TODO: Migrate this function to DataManager
def read_players_into_dict():
    db = Database()
    manager = PlayerManager(db)
    return manager.get_all_players()
