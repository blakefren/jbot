# bot/managers/roles.py
import sys
import os
# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

from db.database import Database
from src.core.base_manager import BaseManager

# TODO: use these role names
ROLE_NAMES = {
    "FIRST_PLACE": "first place",
    "TOP_PLAYER": "top player",
    "RED_TEAM": "red team",
    "BLUE_TEAM": "blue team",
}

class RolesGameMode(BaseManager):
    def __init__(self, db: Database, config):
        self.db = db
        self.config = config

    def on_guess(self, player_id: int, player_name: str, guess: str, is_correct: bool):
        # Role assignments are typically run at the end of a cycle, not on every guess.
        # We can call run() here, or have a separate trigger.
        # For now, let's assume it's run manually or on a schedule.
        pass

    def get_player_scores(self):
        """
        Calculates the score for each player based on the number of correct guesses.
        """
        scores = {}
        # TODO: get from players table instead
        query = "SELECT player_id, COUNT(*) FROM guesses WHERE is_correct = 1 GROUP BY player_id"
        with self.db.get_conn() as conn:
            cursor = conn.execute(query)
            for row in cursor.fetchall():
                player_id, score = row
                scores[player_id] = score
        return scores

    def assign_roles(self):
        """
        Assigns roles to players based on their scores.
        """
        scores = self.get_player_scores()
        if not scores:
            return

        # Sort players by score
        sorted_players = sorted(scores.items(), key=lambda item: item[1], reverse=True)

        # Clear existing roles
        with self.db.get_conn() as conn:
            conn.execute("DELETE FROM player_roles")

        # Assign 'First Place' role
        if sorted_players:
            first_place_player_id = sorted_players[0][0]
            self.assign_role_to_player(first_place_player_id, "First Place")

        # Assign 'Top X%' role
        top_percentage = self.config.get("JBOT_TOP_PLAYER_PERCENTAGE", 10)
        top_n_count = len(sorted_players) * top_percentage // 100
        if top_n_count == 0 and len(sorted_players) > 1:
            top_n_count = 1
        
        for i in range(top_n_count):
            player_id = sorted_players[i][0]
            self.assign_role_to_player(player_id, f"top player")

    def assign_role_to_player(self, player_id, role_name):
        """
        Assigns a role to a player in the database.
        """
        with self.db.get_conn() as conn:
            # Get role_id from role_name
            cursor = conn.execute("SELECT id FROM roles WHERE name = ?", (role_name,))
            role_id_row = cursor.fetchone()
            if role_id_row:
                role_id = role_id_row[0]
            else:
                # If role doesn't exist, create it
                cursor = conn.execute("INSERT INTO roles (name, description) VALUES (?, ?)", (role_name, f"Dynamically created role for {role_name}"))
                role_id = cursor.lastrowid
            
            if role_id:
                conn.execute("INSERT OR IGNORE INTO player_roles (player_id, role_id) VALUES (?, ?)", (player_id, role_id))

    def run(self):
        """
        Runs the role assignment logic.
        """
        self.assign_roles()
