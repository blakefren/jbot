# bot/managers/roles.py
import sys
import os

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

from src.core.data_manager import DataManager
from src.core.base_manager import BaseManager

# TODO: use these role names
ROLE_NAMES = {
    "FIRST_PLACE": "first place",
    "TOP_PLAYER": "top player",
    "RED_TEAM": "red team",
    "BLUE_TEAM": "blue team",
}


class RolesGameMode(BaseManager):
    def __init__(self, data_manager: DataManager, config):
        self.data_manager = data_manager
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
        return self.data_manager.get_player_scores()

    def assign_roles(self):
        """
        Assigns roles to players based on their scores.
        """
        # The list is already sorted by score descending.
        player_scores = self.data_manager.get_player_scores()
        if not player_scores:
            return

        # Clear existing roles
        # TODO: use data_manager method
        with self.data_manager.db.get_conn() as conn:
            conn.execute("DELETE FROM player_roles")

        # Assign 'first place' role to all players tied for first
        if player_scores:
            top_score = player_scores[0]["score"]
            for player in player_scores:
                if player["score"] == top_score:
                    self.assign_role_to_player(player["id"], ROLE_NAMES["FIRST_PLACE"])
                else:
                    # Players are sorted, so we can break early
                    break

        # Assign 'Top X%' role
        top_percentage = self.config.get("JBOT_TOP_PLAYER_PERCENTAGE", 10)
        top_n_count = len(player_scores) * top_percentage // 100
        if top_n_count == 0 and len(player_scores) > 1:
            top_n_count = 1

        for i in range(top_n_count):
            player_id = player_scores[i]["id"]
            self.assign_role_to_player(player_id, ROLE_NAMES["TOP_PLAYER"])

    def assign_role_to_player(self, player_id, role_name):
        """
        Assigns a role to a player in the database.
        """
        # TODO: use data_manager method
        with self.data_manager.db.get_conn() as conn:
            # Get role_id from role_name
            cursor = conn.execute("SELECT id FROM roles WHERE name = ?", (role_name,))
            role_id_row = cursor.fetchone()
            if role_id_row:
                role_id = role_id_row[0]
            else:
                # If role doesn't exist, create it
                cursor = conn.execute(
                    "INSERT INTO roles (name, description) VALUES (?, ?)",
                    (role_name, f"Dynamically created role for {role_name}"),
                )
                role_id = cursor.lastrowid

            if role_id:
                conn.execute(
                    "INSERT OR IGNORE INTO player_roles (player_id, role_id) VALUES (?, ?)",
                    (player_id, role_id),
                )

    def run(self):
        """
        Runs the role assignment logic.
        """
        self.assign_roles()
