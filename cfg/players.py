import csv
import os

PLAYER_FILE_PATH = os.path.join(os.path.dirname(__file__), "players.csv")


class PlayerManager:
    def __init__(self, file_path=PLAYER_FILE_PATH):
        self.file_path = file_path
        self.players = self._load_players()

    def _load_players(self):
        """
        Reads the players CSV file and returns a dictionary of player data.
        """
        players = {}
        try:
            with open(self.file_path, mode="r", newline="", encoding="utf-8") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    discord_id = row.get("discord_id", "").strip()
                    if discord_id:
                        players[discord_id] = {
                            "firstname": row.get("firstname", "").strip(),
                            "lastname": row.get("lastname", "").strip(),
                            "phone_number": row.get("phone_number", "").strip(),
                            "answer_streak": int(row.get("answer_streak", 0)),
                            "active_shield": row.get("active_shield", "False")
                            .strip()
                            .lower()
                            == "true",
                        }
        except FileNotFoundError:
            print(
                f"Warning: Player file not found at '{self.file_path}'. Starting with an empty player list."
            )
        except Exception as e:
            print(f"An unexpected error occurred while loading players: {e}")
        return players

    def get_player(self, discord_id: str):
        return self.players.get(discord_id)

    def get_all_players(self):
        return self.players

    def save_players(self):
        """
        Writes the current player data back to the CSV file.
        """
        try:
            with open(self.file_path, mode="w", newline="", encoding="utf-8") as file:
                fieldnames = [
                    "discord_id",
                    "firstname",
                    "lastname",
                    "phone_number",
                    "answer_streak",
                    "active_shield",
                ]
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                for discord_id, data in self.players.items():
                    row = {"discord_id": discord_id, **data}
                    writer.writerow(row)
        except Exception as e:
            print(f"An unexpected error occurred while saving players: {e}")


# For backwards compatibility
def read_players_into_dict():
    manager = PlayerManager()
    return manager.get_all_players()
