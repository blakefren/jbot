# bot/modes/roles.py
from database.database import Database

# TODO: use these role names
ROLE_NAMES = {
    "FIRST_PLACE": "first place",
    "TOP_PLAYER": "top player",
    "RED_TEAM": "red team",
    "BLUE_TEAM": "blue team",
}

class RolesGameMode:
    def __init__(self, db: Database, config):
        self.db = db
        self.config = config

    def get_player_scores(self):
        """
        Calculates the score for each player based on the number of correct guesses.
        """
        scores = {}
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
        top_percentage = self.config.get("TOP_PLAYER_PERCENTAGE", 10)
        top_n_count = len(sorted_players) * top_percentage // 100
        if top_n_count == 0 and len(sorted_players) > 1:
            top_n_count = 1
        
        for i in range(top_n_count):
            player_id = sorted_players[i][0]
            self.assign_role_to_player(player_id, f"Top {top_percentage}%")

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

            conn.execute("INSERT OR IGNORE INTO player_roles (player_id, role_id) VALUES (?, ?)", (player_id, role_id))

    def run(self):
        """
        Runs the role assignment logic.
        """
        self.assign_roles()
