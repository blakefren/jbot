# bot/managers/roles.py
import sys
import os

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

from src.core.data_manager import DataManager
from src.core.base_manager import BaseManager


class RolesGameMode(BaseManager):
    def __init__(self, data_manager: DataManager, config):
        self.data_manager = data_manager
        self.config = config

    def on_guess(self, player_id: int, player_name: str, guess: str, is_correct: bool):
        # Role assignments are typically run at the end of a cycle, not on every guess.
        # We can call run() here, or have a separate trigger.
        # For now, let's assume it's run manually or on a schedule.
        pass

    def assign_roles(self):
        """
        Assigns roles to players based on their scores.
        """
        # The list is already sorted by score descending.
        player_scores = self.data_manager.get_player_scores()
        if not player_scores:
            return

        # Clear existing roles
        self.data_manager.clear_player_roles()

        # Assign 'first place' role to all players tied for first
        if player_scores:
            top_score = player_scores[0]["score"]
            for player in player_scores:
                if player["score"] == top_score:
                    self.assign_role_to_player(
                        player["id"],
                        self.config.get_string("JBOT_FIRST_PLACE_ROLE_NAME"),
                    )
                else:
                    # Players are sorted, so we can break early
                    break

    def assign_role_to_player(self, player_id, role_name):
        """
        Assigns a role to a player in the database.
        """
        self.data_manager.assign_role_to_player(player_id, role_name)

    def run(self):
        """
        Runs the role assignment logic.
        """
        self.assign_roles()
