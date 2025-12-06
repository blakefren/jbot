from typing import Optional
from datetime import date
from db.database import Database
from data.readers.question import Question
from src.core.player import Player
from src.core.subscriber import Subscriber
import os

# Project root for file paths
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class DataManager:
    """
    Handles all database interactions for the bot.
    """

    def __init__(self, db: "Database"):
        """
        Initializes the data manager, connecting to the database.
        """
        self.db = db

    def initialize_database(self):
        """
        Initializes the database by creating tables from the schema.
        """
        schema_path = os.path.join(_PROJECT_ROOT, "db", "schema.sql")
        with open(schema_path, "r") as f:
            schema = f.read()
        self.db.execute_script(schema)

    def load_players(self) -> dict:
        """
        Reads the players table and returns a dictionary of Player objects keyed by discord_id.
        """
        players = {}
        query = "SELECT id, name, score, answer_streak, active_shield FROM players"
        player_records = self.db.execute_query(query)
        for record in player_records:
            player = Player(
                id=record["id"],
                name=record["name"],
                score=record["score"],
                answer_streak=record["answer_streak"],
                active_shield=bool(record["active_shield"]),
            )
            players[player.id] = player
        return players

    def get_all_players(self) -> dict:
        """
        Reads the players table and returns a dictionary of Player objects keyed by discord_id.
        """
        return self.load_players()

    def get_player(self, player_id: str) -> Optional[Player]:
        """Retrieves a single player from the database."""
        query = "SELECT id, name, score, answer_streak, active_shield FROM players WHERE id = ?"
        result = self.db.execute_query(query, (player_id,))
        if result:
            record = result[0]
            return Player(
                id=record["id"],
                name=record["name"],
                score=record["score"],
                answer_streak=record["answer_streak"],
                active_shield=bool(record["active_shield"]),
            )
        return None

    def create_player(self, player_id: str, name: str):
        """Creates a new player in the database."""
        query = "INSERT INTO players (id, name, score, answer_streak, active_shield) VALUES (?, ?, 0, 0, 0)"
        self.db.execute_update(query, (player_id, name))

    def update_player_name(self, player_id: str, name: str):
        """Updates a player's name."""
        query = "UPDATE players SET name = ? WHERE id = ?"
        self.db.execute_update(query, (name, player_id))

    def increment_streak(self, player_id: str):
        """Atomically increments a player's streak."""
        query = "UPDATE players SET answer_streak = answer_streak + 1 WHERE id = ?"
        self.db.execute_update(query, (player_id,))

    def reset_streak(self, player_id: str):
        """Resets a player's streak to 0."""
        query = "UPDATE players SET answer_streak = 0 WHERE id = ?"
        self.db.execute_update(query, (player_id,))

    def set_shield(self, player_id: str, active: bool):
        """Sets a player's shield status."""
        query = "UPDATE players SET active_shield = ? WHERE id = ?"
        self.db.execute_update(query, (active, player_id))

    def adjust_player_score(self, player_id: str, amount: int):
        """
        Adjusts a player's score by a given amount.

        Args:
            player_id (str): The unique identifier for the player.
            amount (int): The amount to adjust the score by (can be negative).
        """
        query = "UPDATE players SET score = score + ? WHERE id = ?"
        self.db.execute_update(query, (amount, player_id))

    def log_daily_question(self, question: Question, force_new: bool = False):
        """
        Logs details about a daily question that was sent out.

        Args:
            question (Question): The question object.
            force_new (bool): If True, will replace today's question if one exists.
        """
        # First, ensure the question exists in the 'questions' table
        question_query = "SELECT id FROM questions WHERE question_hash = ?"
        existing_question = self.db.execute_query(question_query, (str(question.id),))

        if existing_question:
            question_id = existing_question[0]["id"]
        else:
            # Insert the new question and get its ID
            insert_query = """
                INSERT INTO questions (question_text, answer_text, category, value, source, hint_text, question_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            _, question_id = self.db.execute_update(
                insert_query,
                (
                    question.question,
                    question.answer,
                    question.category,
                    question.clue_value,
                    question.data_source,
                    question.hint,
                    str(question.id),  # Hash
                ),
            )

        # Check if a daily question has already been logged for today
        today = date.today()
        daily_question_info = self.get_todays_daily_question()

        if daily_question_info:
            _, daily_question_id = daily_question_info
            if force_new:
                # Update the existing daily question entry for today
                update_query = (
                    "UPDATE daily_questions SET question_id = ? WHERE sent_at = ?"
                )
                self.db.execute_update(update_query, (question_id, today))
                return daily_question_id
            else:
                return daily_question_id

        # Log the daily question event
        daily_question_query = (
            "INSERT INTO daily_questions (question_id, sent_at) VALUES (?, ?)"
        )
        _, daily_question_id = self.db.execute_update(
            daily_question_query, (question_id, today)
        )

        return daily_question_id

    def log_player_guess(
        self,
        player_id: str,
        player_name: str,
        question_id: str,
        guess: str,
        is_correct: bool,
    ):
        """
        Logs a player's guess for a question.

        Args:
            player_id (str): The unique identifier for the player.
            player_name (str): The display name of the player.
            question_id (str): The unique identifier for the daily question.
            guess (str): The answer submitted by the player.
            is_correct (bool): Whether the guess was correct.
        """
        self.db.execute_update(
            "INSERT OR IGNORE INTO players (id, name) VALUES (?, ?)",
            (player_id, player_name),
        )

        query = """
            INSERT INTO guesses (daily_question_id, player_id, guess_text, is_correct)
            VALUES (?, ?, ?, ?)
        """
        self.db.execute_update(query, (question_id, player_id, guess, is_correct))

    def log_messaging_event(
        self, direction, method, recipient_or_sender, content, status="success"
    ):
        """
        Logs details about any message sent by the bot.
        """
        if direction != "outgoing":
            return

        query = """
            INSERT INTO messages (direction, method, recipient_sender, content, status)
            VALUES (?, ?, ?, ?, ?)
        """
        self.db.execute_update(
            query, (direction, method, recipient_or_sender, content, status)
        )

    def get_player_scores(self) -> list[dict]:
        """
        Retrieves player ids, names and scores from the database, ordered by score.
        """
        query = (
            "SELECT id, name, score FROM players WHERE score > 0 ORDER BY score DESC"
        )
        return self.db.execute_query(query)

    def get_player_streaks(self) -> list[dict]:
        """
        Retrieves player ids, names and answer streaks from the database, ordered by streak.
        """
        query = "SELECT id, name, answer_streak FROM players WHERE answer_streak > 1 ORDER BY answer_streak DESC"
        return self.db.execute_query(query)

    def get_player_ids_with_role(self, role_name: str) -> set[int]:
        """
        Retrieves the player IDs for a given role name.

        Args:
            role_name (str): The name of the role to check.

        Returns:
            set[int]: A set of player IDs that have the role.
        """
        query = "SELECT player_id FROM player_roles pr JOIN roles r ON pr.role_id = r.id WHERE r.name = ?"
        result = self.db.execute_query(query, (role_name,))
        return {row["player_id"] for row in result}

    def get_all_subscribers(self) -> set[Subscriber]:
        """Gets all subscribers from the database."""
        rows = self.db.execute_query(
            "SELECT id, display_name, is_channel FROM subscribers"
        )
        return {
            Subscriber(row["id"], row["display_name"], row["is_channel"])
            for row in rows
        }

    def save_subscriber(self, subscriber: Subscriber):
        """Saves the subscriber to the database."""
        self.db.execute_update(
            "INSERT OR REPLACE INTO subscribers (id, display_name, is_channel) VALUES (?, ?, ?)",
            (subscriber.sub_id, subscriber.display_name, subscriber.is_channel),
        )

    def delete_subscriber(self, subscriber: Subscriber):
        """Deletes the subscriber from the database."""
        self.db.execute_update(
            "DELETE FROM subscribers WHERE id = ?", (subscriber.sub_id,)
        )

    def read_guess_history(self, user_id: int = -1) -> list[dict]:
        """
        Reads and parses the guess history from the database.
        """
        query = """
            SELECT g.*, p.name as player_name
            FROM guesses g
            JOIN players p ON g.player_id = p.id
        """
        params = ()
        if user_id != -1:
            query += " WHERE g.player_id = ?"
            params = (user_id,)

        return self.db.execute_query(query, params)

    def get_question_by_id(self, question_id: int) -> Optional[Question]:
        """
        Retrieves a question from the database by its ID.
        """
        query = "SELECT * FROM questions WHERE id = ?"
        result = self.db.execute_query(query, (question_id,))
        if not result:
            return None

        q_data = result[0]
        return Question(
            question=q_data["question_text"],
            answer=q_data["answer_text"],
            category=q_data["category"],
            clue_value=q_data["value"],
            data_source=q_data["source"],
            hint=q_data["hint_text"],
        )

    def get_todays_daily_question(self) -> Optional[tuple[Question, int]]:
        """
        Retrieves today's daily question as a Question object and its ID.
        If multiple questions exist for today (e.g., from skip), returns the newest.
        """
        today = date.today()
        query = "SELECT id, question_id FROM daily_questions WHERE sent_at = ? ORDER BY id DESC LIMIT 1"
        daily_question_info = self.db.execute_query(query, (today,))

        if not daily_question_info:
            return None

        daily_question_info = daily_question_info[0]

        question = self.get_question_by_id(daily_question_info["question_id"])
        daily_question_id = daily_question_info["id"]

        if not question:
            return None

        return question, daily_question_id

    def get_used_question_hashes(self) -> set[str]:
        """
        Retrieves all question hashes that have been used as daily questions.

        Returns:
            set[str]: A set of question hashes that have been previously used.
        """
        query = """
            SELECT DISTINCT q.question_hash
            FROM daily_questions dq
            JOIN questions q ON dq.question_id = q.id
        """
        results = self.db.execute_query(query)
        if not results:
            return set()
        return {row["question_hash"] for row in results}

    def assign_role_to_player(self, player_id: str, role_name: str):
        """
        Assigns a role to a player in the database, creating the role if it doesn't exist.
        """
        # This method combines getting/creating the role and assigning it.
        # It's not transactional, but for this use case, it's acceptable.

        # Get role_id from role_name
        role_id_row = self.db.execute_query(
            "SELECT id FROM roles WHERE name = ?", (role_name,)
        )
        if role_id_row:
            role_id = role_id_row[0]["id"]
        else:
            # If role doesn't exist, create it
            _, role_id = self.db.execute_update(
                "INSERT INTO roles (name, description) VALUES (?, ?)",
                (role_name, f"Dynamically created role for {role_name}"),
            )

        if role_id:
            self.db.execute_update(
                "INSERT OR IGNORE INTO player_roles (player_id, role_id) VALUES (?, ?)",
                (player_id, role_id),
            )

    def clear_player_roles(self):
        """
        Deletes all records from the player_roles table.
        """
        query = "DELETE FROM player_roles"
        self.db.execute_update(query)

    def log_score_adjustment(
        self, player_id: str, admin_id: str, amount: int, reason: str
    ):
        """
        Logs a score adjustment for a player.

        Args:
            player_id (str): The unique identifier for the player.
            admin_id (str): The unique identifier for the admin making the adjustment.
            amount (int): The amount adjusted (positive or negative).
            reason (str): The reason for the adjustment.
        """
        query = """
            INSERT INTO score_adjustments (player_id, admin_id, amount, reason)
            VALUES (?, ?, ?, ?)
        """
        self.db.execute_update(query, (player_id, admin_id, amount, reason))

    def get_hint_sent_timestamp(self, daily_question_id: int) -> Optional[str]:
        """
        Retrieves the timestamp for when a hint was sent for a specific daily question.

        Args:
            daily_question_id (int): The ID of the daily question.

        Returns:
            Optional[str]: The timestamp of the hint message, or None if not found.
        """
        query = """
            SELECT timestamp FROM messages
            WHERE status = 'reminder_message' AND date(timestamp) = (
                SELECT sent_at FROM daily_questions WHERE id = ?
            )
            ORDER BY timestamp DESC
            LIMIT 1
        """
        result = self.db.execute_query(query, (daily_question_id,))
        return result[0]["timestamp"] if result else None

    def get_first_try_solvers(self, daily_question_id: int) -> list[dict]:
        """
        Retrieves players who got the answer right on their first try for the day.

        Args:
            daily_question_id (int): The ID of the daily question.

        Returns:
            list[dict]: A list of dictionaries with player 'id' and 'name'.
        """
        query = """
            SELECT p.id, p.name
            FROM guesses g
            JOIN players p ON g.player_id = p.id
            WHERE g.daily_question_id = ? AND g.is_correct = 1
            GROUP BY p.id, p.name
            HAVING COUNT(g.id) = 1
        """
        return self.db.execute_query(query, (daily_question_id,))

    def get_guess_counts_per_player(self, daily_question_id: int) -> list[dict]:
        """
        Gets the number of unique guesses per player for the day.

        Args:
            daily_question_id (int): The ID of the daily question.

        Returns:
            list[dict]: A list of dictionaries with player 'name' and 'guess_count'.
        """
        query = """
            SELECT p.name, COUNT(DISTINCT g.guess_text) as guess_count
            FROM guesses g
            JOIN players p ON g.player_id = p.id
            WHERE g.daily_question_id = ?
            GROUP BY g.player_id, p.name
            ORDER BY guess_count DESC
        """
        return self.db.execute_query(query, (daily_question_id,))

    def get_most_common_guesses(self, daily_question_id: int) -> list[dict]:
        """
        Finds the most common incorrect guesses for the day.

        Args:
            daily_question_id (int): The ID of the daily question.

        Returns:
            list[dict]: A list of dictionaries with 'guess_text' and 'count'.
        """
        query = """
            SELECT guess_text, COUNT(*) as count
            FROM guesses
            WHERE daily_question_id = ? AND is_correct = 0
            GROUP BY guess_text
            ORDER BY count DESC
            LIMIT 5
        """
        return self.db.execute_query(query, (daily_question_id,))

    def get_craziest_guess(self, daily_question_id: int) -> Optional[dict]:
        """
        Finds the 'craziest' guess of the day (currently defined as the longest).

        Args:
            daily_question_id (int): The ID of the daily question.

        Returns:
            Optional[dict]: A dictionary with 'player_name' and 'guess_text', or None.
        """
        query = """
            SELECT p.name as player_name, g.guess_text
            FROM guesses g
            JOIN players p ON g.player_id = p.id
            WHERE g.daily_question_id = ?
            ORDER BY LENGTH(g.guess_text) DESC
            LIMIT 1
        """
        result = self.db.execute_query(query, (daily_question_id,))
        return result[0] if result else None

    def get_solvers_before_hint(self, daily_question_id: int) -> list[dict]:
        """
        Retrieves players who solved the question before the hint was sent.

        Args:
            daily_question_id (int): The ID of the daily question.

        Returns:
            list[dict]: A list of dictionaries with player 'id' and 'name'.
        """
        hint_timestamp = self.get_hint_sent_timestamp(daily_question_id)
        if not hint_timestamp:
            return []

        query = """
            SELECT p.id, p.name
            FROM guesses g
            JOIN players p ON g.player_id = p.id
            WHERE g.daily_question_id = ? AND g.is_correct = 1 AND g.guessed_at < ?
            GROUP BY p.id, p.name
        """
        return self.db.execute_query(query, (daily_question_id, hint_timestamp))

    def get_solvers_after_hint(self, daily_question_id: int) -> list[dict]:
        """
        Retrieves players who only guessed after the hint was sent.

        Args:
            daily_question_id (int): The ID of the daily question.

        Returns:
            list[dict]: A list of dictionaries with player 'id' and 'name'.
        """
        hint_timestamp = self.get_hint_sent_timestamp(daily_question_id)
        if not hint_timestamp:
            return []

        query = """
            SELECT p.id, p.name
            FROM players p
            WHERE p.id IN (
                -- Players who have a correct guess after the hint
                SELECT DISTINCT g.player_id
                FROM guesses g
                WHERE g.daily_question_id = ? AND g.is_correct = 1 AND g.guessed_at > ?
            ) AND p.id NOT IN (
                -- Exclude players who had any guess (correct or incorrect) before the hint
                SELECT DISTINCT g.player_id
                FROM guesses g
                WHERE g.daily_question_id = ? AND g.guessed_at < ?
            )
        """
        return self.db.execute_query(
            query,
            (daily_question_id, hint_timestamp, daily_question_id, hint_timestamp),
        )

    def get_correct_guess_count(self, daily_question_id: int) -> int:
        """
        Returns the number of correct guesses for a specific daily question.
        """
        query = "SELECT COUNT(*) as count FROM guesses WHERE daily_question_id = ? AND is_correct = 1"
        result = self.db.execute_query(query, (daily_question_id,))
        return result[0]["count"] if result else 0
