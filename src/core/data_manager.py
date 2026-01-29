from datetime import date, datetime
from db.database import Database
from data.readers.question import Question
from src.core.player import Player
from src.core.subscriber import Subscriber
import os
import logging

# Project root for file paths
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class DataManager:
    """
    Handles all database interactions for the bot.
    This is the ONLY class that should directly access the database.
    All other components must use DataManager methods for database operations.
    """

    def __init__(self, db: "Database"):
        """
        Initializes the data manager, connecting to the database.

        Args:
            db: Database instance. This is stored as a private attribute (_db)
                to prevent direct access from outside this class.
        """
        self._db = db

    def initialize_database(self):
        """
        Initializes the database by creating tables from the schema.
        """
        schema_path = os.path.join(_PROJECT_ROOT, "db", "schema.sql")
        with open(schema_path, "r") as f:
            schema = f.read()
        self._db.execute_script(schema)

    def load_players(self) -> dict:
        """
        Reads the players table and returns a dictionary of Player objects keyed by discord_id.
        """
        players = {}
        query = """
            SELECT id, name, score, season_score, answer_streak, active_shield,
                   lifetime_questions, lifetime_correct, lifetime_first_answers, lifetime_best_streak
            FROM players
        """
        player_records = self._db.execute_query(query)
        for record in player_records:
            player = Player(
                id=record["id"],
                name=record["name"],
                score=record.get("score", 0),
                season_score=record.get("season_score", 0),
                answer_streak=record.get("answer_streak", 0),
                active_shield=bool(record.get("active_shield", False)),
                lifetime_questions=record.get("lifetime_questions", 0),
                lifetime_correct=record.get("lifetime_correct", 0),
                lifetime_first_answers=record.get("lifetime_first_answers", 0),
                lifetime_best_streak=record.get("lifetime_best_streak", 0),
            )
            players[player.id] = player
        return players

    def get_all_players(self) -> dict:
        """
        Reads the players table and returns a dictionary of Player objects keyed by discord_id.
        """
        return self.load_players()

    def get_player(self, player_id: str) -> Player | None:
        """Retrieves a single player from the database."""
        query = """
            SELECT id, name, score, season_score, answer_streak, active_shield,
                   lifetime_questions, lifetime_correct, lifetime_first_answers, lifetime_best_streak
            FROM players
            WHERE id = ?
        """
        result = self._db.execute_query(query, (player_id,))
        if result:
            record = result[0]
            return Player(
                id=record["id"],
                name=record["name"],
                score=record.get("score", 0),
                season_score=record.get("season_score", 0),
                answer_streak=record.get("answer_streak", 0),
                active_shield=bool(record.get("active_shield", False)),
                lifetime_questions=record.get("lifetime_questions", 0),
                lifetime_correct=record.get("lifetime_correct", 0),
                lifetime_first_answers=record.get("lifetime_first_answers", 0),
                lifetime_best_streak=record.get("lifetime_best_streak", 0),
            )
        return None

    def create_player(self, player_id: str, name: str):
        """Creates a new player in the database."""
        query = """
            INSERT INTO players (id, name, score, season_score, answer_streak, active_shield,
                                lifetime_questions, lifetime_correct, lifetime_first_answers, lifetime_best_streak)
            VALUES (?, ?, 0, 0, 0, 0, 0, 0, 0, 0)
        """
        self._db.execute_update(query, (player_id, name))

    def update_player_name(self, player_id: str, name: str):
        """Updates a player's name."""
        query = "UPDATE players SET name = ? WHERE id = ?"
        self._db.execute_update(query, (name, player_id))

    def increment_streak(self, player_id: str):
        """Atomically increments a player's streak."""
        query = "UPDATE players SET answer_streak = answer_streak + 1 WHERE id = ?"
        self._db.execute_update(query, (player_id,))

    def reset_streak(self, player_id: str):
        """Resets a player's streak to 0."""
        query = "UPDATE players SET answer_streak = 0 WHERE id = ?"
        self._db.execute_update(query, (player_id,))

    def set_streak(self, player_id: str, streak: int):
        """Sets a player's streak to a specific value."""
        query = "UPDATE players SET answer_streak = ? WHERE id = ?"
        self._db.execute_update(query, (streak, player_id))

    def set_shield(self, player_id: str, active: bool):
        """Sets a player's shield status."""
        query = "UPDATE players SET active_shield = ? WHERE id = ?"
        self._db.execute_update(query, (active, player_id))

    def adjust_player_score(self, player_id: str, amount: int):
        """
        Adjusts a player's score by a given amount.

        Args:
            player_id (str): The unique identifier for the player.
            amount (int): The amount to adjust the score by (can be negative).
        """
        query = "UPDATE players SET score = score + ? WHERE id = ?"
        self._db.execute_update(query, (amount, player_id))

    def log_daily_question(
        self,
        question: Question,
        force_new: bool = False,
        mark_as_used_only: bool = False,
    ):
        """
        Logs details about a daily question that was sent out.

        Args:
            question (Question): The question object.
            force_new (bool): If True, will replace today's question if one exists.
            mark_as_used_only (bool): If True, only adds to questions table (marking as used) but not daily_questions.
        """
        # First, ensure the question exists in the 'questions' table
        question_query = "SELECT id FROM questions WHERE question_hash = ?"
        existing_question = self._db.execute_query(question_query, (str(question.id),))

        if existing_question:
            question_id = existing_question[0]["id"]
        else:
            # Insert the new question and get its ID
            insert_query = """
                INSERT INTO questions (question_text, answer_text, category, value, source, hint_text, question_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            _, question_id = self._db.execute_update(
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

        if mark_as_used_only:
            return None

        # Check if a daily question has already been logged for today
        today = date.today()
        daily_question_info = self.get_todays_daily_question()

        if daily_question_info and not force_new:
            _, daily_question_id, _ = daily_question_info
            return daily_question_id

        # Log the daily question event
        daily_question_query = (
            "INSERT INTO daily_questions (question_id, sent_at) VALUES (?, ?)"
        )
        _, daily_question_id = self._db.execute_update(
            daily_question_query, (question_id, today)
        )

        # Create a snapshot of player states for this new daily question
        self.create_daily_snapshot(daily_question_id)

        return daily_question_id

    def update_daily_question_hint(self, daily_question_id: int, hint: str):
        """
        Updates the hint text for a daily question.

        Args:
            daily_question_id (int): The daily question ID.
            hint (str): The new hint text.
        """
        # Get the question_id from daily_questions
        query = "SELECT question_id FROM daily_questions WHERE id = ?"
        result = self._db.execute_query(query, (daily_question_id,))

        if not result:
            logging.error(f"Daily question ID {daily_question_id} not found")
            return

        question_id = result[0]["question_id"]

        # Update the hint in the questions table
        update_query = "UPDATE questions SET hint_text = ? WHERE id = ?"
        self._db.execute_update(update_query, (hint, question_id))
        logging.info(f"Updated hint for question {question_id}")

    def create_daily_snapshot(self, daily_question_id: int):
        """
        Creates a snapshot of all players' current state (score, streak)
        associated with the given daily_question_id.
        """
        # Get all current players
        players = self.load_players()

        if not players:
            return

        query = """
            INSERT INTO daily_player_states (daily_question_id, player_id, score, answer_streak)
            VALUES (?, ?, ?, ?)
        """

        for player in players.values():
            try:
                self._db.execute_update(
                    query,
                    (daily_question_id, player.id, player.score, player.answer_streak),
                )
            except Exception as e:
                # Log error but continue for other players
                # In a real scenario, we might want to be more aggressive, but we don't have a logger here easily accessible
                # actually logging is imported in other files, let's check imports
                print(f"Failed to snapshot player {player.id}: {e}")

    def get_daily_snapshot(self, daily_question_id: int) -> dict[str, Player]:
        """
        Retrieves the player state snapshot for a specific daily question.
        Returns a dictionary of Player objects keyed by player_id.
        """
        query = """
            SELECT dps.player_id, dps.score, dps.answer_streak, p.name
            FROM daily_player_states dps
            LEFT JOIN players p ON dps.player_id = p.id
            WHERE dps.daily_question_id = ?
        """
        records = self._db.execute_query(query, (daily_question_id,))

        snapshot = {}
        for record in records:
            player_id = record["player_id"]
            name = record["name"] if record["name"] else "Unknown"

            snapshot[player_id] = Player(
                id=player_id,
                name=name,
                score=record["score"],
                answer_streak=record["answer_streak"],
                active_shield=False,
            )

        return snapshot

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
        self._db.execute_update(
            "INSERT OR IGNORE INTO players (id, name) VALUES (?, ?)",
            (player_id, player_name),
        )

        query = """
            INSERT INTO guesses (daily_question_id, player_id, guess_text, is_correct)
            VALUES (?, ?, ?, ?)
        """
        self._db.execute_update(query, (question_id, player_id, guess, is_correct))

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
        self._db.execute_update(
            query, (direction, method, recipient_or_sender, content, status)
        )

    def get_player_scores(self) -> list[dict]:
        """
        Retrieves player ids, names and scores from the database, ordered by score.
        Excludes players who haven't guessed in the last 28 days.
        """
        query = """
            SELECT p.id, p.name, p.score
            FROM players p
            WHERE p.score > 0
            AND EXISTS (
                SELECT 1
                FROM guesses g
                WHERE g.player_id = p.id
                AND g.guessed_at >= datetime('now', '-28 days')
            )
            ORDER BY p.score DESC
        """
        return self._db.execute_query(query)

    def get_player_streaks(self) -> list[dict]:
        """
        Retrieves player ids, names and answer streaks from the database, ordered by streak.
        Only includes streaks that are active (streak > 0).
        """
        query = """
            SELECT id, name, answer_streak
            FROM players
            WHERE answer_streak > 0
            ORDER BY answer_streak DESC
        """
        return self._db.execute_query(query)

    def reset_unanswered_streaks(self, daily_question_id: int):
        """
        Resets the answer streak to 0 for all players who did not have a correct guess
        for the specified daily question.
        """
        query = """
            UPDATE players
            SET answer_streak = 0
            WHERE id NOT IN (
                SELECT player_id
                FROM guesses
                WHERE daily_question_id = ? AND is_correct = 1
            )
            AND answer_streak > 0
        """
        self._db.execute_update(query, (daily_question_id,))

    def get_player_ids_with_role(self, role_name: str) -> set[int]:
        """
        Retrieves the player IDs for a given role name.

        Args:
            role_name (str): The name of the role to check.

        Returns:
            set[int]: A set of player IDs that have the role.
        """
        query = "SELECT player_id FROM player_roles pr JOIN roles r ON pr.role_id = r.id WHERE r.name = ?"
        result = self._db.execute_query(query, (role_name,))
        return {row["player_id"] for row in result}

    def get_all_subscribers(self) -> set[Subscriber]:
        """Gets all subscribers from the database."""
        rows = self._db.execute_query(
            "SELECT id, display_name, is_channel FROM subscribers"
        )
        return {
            Subscriber(row["id"], row["display_name"], row["is_channel"])
            for row in rows
        }

    def save_subscriber(self, subscriber: Subscriber):
        """Saves the subscriber to the database."""
        self._db.execute_update(
            "INSERT OR REPLACE INTO subscribers (id, display_name, is_channel) VALUES (?, ?, ?)",
            (subscriber.sub_id, subscriber.display_name, subscriber.is_channel),
        )

    def delete_subscriber(self, subscriber: Subscriber):
        """Deletes the subscriber from the database."""
        self._db.execute_update(
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

        return self._db.execute_query(query, params)

    def get_question_by_id(self, question_id: int) -> Optional[Question]:
        """
        Retrieves a question from the database by its ID.
        """
        query = "SELECT * FROM questions WHERE id = ?"
        result = self._db.execute_query(query, (question_id,))
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

    def get_todays_daily_question(self) -> Optional[tuple[Question, int, int]]:
        """
        Retrieves today's daily question as a Question object and its IDs.
        If multiple questions exist for today (e.g., from skip), returns the newest.

        Returns:
            Optional[tuple[Question, int, int]]: (Question object, daily_question_id, question_id) or None
        """
        today = date.today()
        query = "SELECT id, question_id FROM daily_questions WHERE sent_at = ? ORDER BY id DESC LIMIT 1"
        daily_question_info = self._db.execute_query(query, (today,))

        if not daily_question_info:
            return None

        daily_question_info = daily_question_info[0]

        question = self.get_question_by_id(daily_question_info["question_id"])
        daily_question_id = daily_question_info["id"]
        question_id = daily_question_info["question_id"]

        if not question:
            return None

        return question, daily_question_id, question_id

    def get_most_recent_daily_question(self) -> Optional[tuple[Question, int, date]]:
        """
        Retrieves the most recent daily question from the database, regardless of date.
        Returns the Question object, its daily_question_id, and the date it was sent.
        """
        query = "SELECT id, question_id, sent_at FROM daily_questions ORDER BY id DESC LIMIT 1"
        daily_question_info = self._db.execute_query(query)

        if not daily_question_info:
            return None

        daily_question_info = daily_question_info[0]

        question = self.get_question_by_id(daily_question_info["question_id"])
        daily_question_id = daily_question_info["id"]
        sent_at = (
            date.fromisoformat(daily_question_info["sent_at"])
            if isinstance(daily_question_info["sent_at"], str)
            else daily_question_info["sent_at"]
        )

        if not question:
            return None

        return question, daily_question_id, sent_at

    def get_recent_answers(self, limit: int = 7) -> list[str]:
        """
        Retrieves a list of answers from the most recent daily questions.

        Args:
            limit: The number of recent days to look back.

        Returns:
            list[str]: A list of answer strings.
        """
        query = """
        SELECT q.answer_text
        FROM daily_questions dq
        JOIN questions q ON dq.question_id = q.id
        ORDER BY dq.sent_at DESC
        LIMIT ?
        """
        results = self._db.execute_query(query, (limit,))
        return [row["answer_text"] for row in results]

    def get_used_question_hashes(self) -> set[str]:
        """
        Retrieves all question hashes that have been used as daily questions.

        Returns:
            set[str]: A set of question hashes that have been previously used.
        """
        query = "SELECT question_hash FROM questions"
        results = self._db.execute_query(query)
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
        role_id_row = self._db.execute_query(
            "SELECT id FROM roles WHERE name = ?", (role_name,)
        )
        if role_id_row:
            role_id = role_id_row[0]["id"]
        else:
            # If role doesn't exist, create it
            _, role_id = self._db.execute_update(
                "INSERT INTO roles (name, description) VALUES (?, ?)",
                (role_name, f"Dynamically created role for {role_name}"),
            )

        if role_id:
            self._db.execute_update(
                "INSERT OR IGNORE INTO player_roles (player_id, role_id) VALUES (?, ?)",
                (player_id, role_id),
            )

    def clear_player_roles(self):
        """
        Deletes all records from the player_roles table.
        """
        query = "DELETE FROM player_roles"
        self._db.execute_update(query)

    def log_powerup_usage(
        self,
        user_id: str,
        powerup_type: str,
        target_user_id: str = None,
        question_id: int = None,
    ):
        """Logs a powerup usage."""
        query = "INSERT INTO powerup_usage (user_id, powerup_type, target_user_id, question_id) VALUES (?, ?, ?, ?)"
        self._db.execute_update(
            query, (user_id, powerup_type, target_user_id, question_id)
        )

    def get_powerup_usages_for_question(self, question_id: int) -> list[dict]:
        """Retrieves powerup usages for a specific question."""
        query = "SELECT * FROM powerup_usage WHERE question_id = ?"
        results = self._db.execute_query(query, (question_id,))
        return results

    # TODO: log streak adjustment as well
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
        self._db.execute_update(query, (player_id, admin_id, amount, reason))

    def add_alternative_answer(self, question_id: int, answer_text: str, admin_id: str):
        """Adds an alternative correct answer for a question."""
        query = "INSERT INTO alternative_answers (question_id, answer_text, added_by) VALUES (?, ?, ?)"
        self._db.execute_update(query, (question_id, answer_text, admin_id))

    def get_alternative_answers(self, question_id: int) -> list[str]:
        """Retrieves all alternative answers for a question."""
        query = "SELECT answer_text FROM alternative_answers WHERE question_id = ?"
        results = self._db.execute_query(query, (question_id,))
        return [r["answer_text"] for r in results]

    def get_guesses_for_daily_question(self, daily_question_id: int) -> list[dict]:
        """Retrieves all guesses for a specific daily question."""
        query = (
            "SELECT * FROM guesses WHERE daily_question_id = ? ORDER BY guessed_at ASC"
        )
        return self._db.execute_query(query, (daily_question_id,))

    def get_hint_sent_timestamp(self, daily_question_id: int) -> Optional[str]:
        """
        Retrieves the timestamp for when a hint was sent for a specific daily question.
        Uses the morning message as a reference point to ensure we get the correct day's hint,
        handling timezone differences where the hint might fall on the next UTC day.

        Args:
            daily_question_id (int): The ID of the daily question.

        Returns:
            Optional[str]: The timestamp of the hint message, or None if not found.
        """
        query = """
            SELECT m.timestamp
            FROM messages m
            WHERE m.status = 'reminder_message'
              AND m.timestamp > (
                  SELECT MIN(m2.timestamp)
                  FROM messages m2
                  JOIN daily_questions dq ON dq.id = ?
                  WHERE m2.status = 'morning_message'
                    AND m2.timestamp >= dq.sent_at
                    AND m2.timestamp < date(dq.sent_at, '+2 days')
              )
            ORDER BY m.timestamp DESC
            LIMIT 1
        """
        result = self._db.execute_query(query, (daily_question_id,))
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
            WHERE g.daily_question_id = ?
            GROUP BY p.id, p.name
            HAVING COUNT(g.id) = 1 AND MAX(g.is_correct) = 1
        """
        return self._db.execute_query(query, (daily_question_id,))

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
        return self._db.execute_query(query, (daily_question_id,))

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
        return self._db.execute_query(query, (daily_question_id,))

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
        result = self._db.execute_query(query, (daily_question_id,))
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
        return self._db.execute_query(query, (daily_question_id, hint_timestamp))

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
        return self._db.execute_query(
            query,
            (daily_question_id, hint_timestamp, daily_question_id, hint_timestamp),
        )

    def get_correct_guess_count(self, daily_question_id: int) -> int:
        """
        Returns the number of correct guesses for a specific daily question.
        """
        query = "SELECT COUNT(*) as count FROM guesses WHERE daily_question_id = ? AND is_correct = 1"
        result = self._db.execute_query(query, (daily_question_id,))
        return result[0]["count"] if result else 0

    def get_last_correct_guess_date(self, player_id: str) -> Optional[date]:
        """
        Retrieves the date of the last correct guess for a player.
        """
        query = """
            SELECT dq.sent_at
            FROM guesses g
            JOIN daily_questions dq ON g.daily_question_id = dq.id
            WHERE g.player_id = ? AND g.is_correct = 1
            ORDER BY dq.sent_at DESC
            LIMIT 1
        """
        result = self._db.execute_query(query, (player_id,))
        if result:
            date_str = result[0]["sent_at"]
            if isinstance(date_str, str):
                return datetime.strptime(date_str, "%Y-%m-%d").date()
            return date_str  # In case it's already a date object
        return None

    def mark_guess_as_correct(self, guess_id: int):
        """
        Updates a specific guess to be marked as correct.
        """
        query = "UPDATE guesses SET is_correct = 1 WHERE id = ?"
        self._db.execute_update(query, (guess_id,))

    def mark_matching_guesses_as_correct(
        self, daily_question_id: str, new_answer: str, match_func
    ) -> int:
        """
        Marks previously incorrect guesses as correct if they match the new answer.

        Args:
            daily_question_id: The ID of the daily question
            new_answer: The new alternative answer to check against
            match_func: A callable that takes (guess_text, answer_text) and returns bool

        Returns:
            int: Number of guesses marked as correct
        """
        # Get all incorrect guesses for this question
        query = """
            SELECT id, guess_text
            FROM guesses
            WHERE daily_question_id = ? AND is_correct = 0
        """
        guesses = self._db.execute_query(query, (daily_question_id,))

        # Check each guess against the new answer
        guess_ids_to_update = []

        for guess in guesses:
            guess_text = guess.get("guess_text")
            if guess_text:
                if match_func(guess_text, new_answer):
                    guess_ids_to_update.append(guess["id"])

        # Update all matching guesses to is_correct = 1
        if guess_ids_to_update:
            placeholders = ",".join("?" * len(guess_ids_to_update))
            update_query = (
                f"UPDATE guesses SET is_correct = 1 WHERE id IN ({placeholders})"
            )
            self._db.execute_update(update_query, tuple(guess_ids_to_update))

        return len(guess_ids_to_update)

    # ==================== SEASONS FEATURE METHODS ====================

    def get_current_season(self):
        """Get the current active season, if any."""
        from src.core.season import Season

        query = "SELECT * FROM seasons WHERE is_active = 1 LIMIT 1"
        result = self._db.execute_query(query)
        if result:
            return Season.from_db_row(result[0])
        return None

    def create_season(self, season_name: str, start_date: str, end_date: str) -> int:
        """
        Create a new season.

        Args:
            season_name: Display name (e.g., "January 2026")
            start_date: ISO8601 date string (e.g., "2026-01-01")
            end_date: ISO8601 date string (e.g., "2026-01-31")

        Returns:
            season_id of the newly created season
        """
        # Deactivate any currently active seasons
        self._db.execute_update("UPDATE seasons SET is_active = 0 WHERE is_active = 1")

        query = """
            INSERT INTO seasons (season_name, start_date, end_date, is_active)
            VALUES (?, ?, ?, 1)
        """
        cursor = self._db.execute_update(query, (season_name, start_date, end_date))
        return cursor.lastrowid

    def get_season_by_id(self, season_id: int):
        """Get a specific season by ID."""
        from src.core.season import Season

        query = "SELECT * FROM seasons WHERE season_id = ?"
        result = self._db.execute_query(query, (season_id,))
        if result:
            return Season.from_db_row(result[0])
        return None

    def get_all_seasons(self, order_by: str = "start_date DESC"):
        """Get all seasons, ordered by specified column."""
        from src.core.season import Season

        query = f"SELECT * FROM seasons ORDER BY {order_by}"
        result = self._db.execute_query(query)
        return [Season.from_db_row(row) for row in result]

    def end_season(self, season_id: int):
        """Mark a season as inactive (ended)."""
        query = "UPDATE seasons SET is_active = 0 WHERE season_id = ?"
        self._db.execute_update(query, (season_id,))

    def get_season_scores(self, season_id: int, limit: int = 10):
        """
        Get player scores for a season, ordered by points descending.

        Returns:
            List of SeasonScore objects
        """
        from src.core.season import SeasonScore

        query = """
            SELECT * FROM season_scores
            WHERE season_id = ?
            ORDER BY points DESC
            LIMIT ?
        """
        result = self._db.execute_query(query, (season_id, limit))
        return [SeasonScore.from_db_row(row) for row in result]

    def get_player_season_score(self, player_id: str, season_id: int):
        """Get a specific player's season score."""
        from src.core.season import SeasonScore

        query = """
            SELECT * FROM season_scores
            WHERE player_id = ? AND season_id = ?
        """
        result = self._db.execute_query(query, (player_id, season_id))
        if result:
            return SeasonScore.from_db_row(result[0])
        return None

    def initialize_player_season_score(self, player_id: str, season_id: int):
        """Create a season_scores record for a player if it doesn't exist."""
        existing = self.get_player_season_score(player_id, season_id)
        if not existing:
            query = """
                INSERT INTO season_scores (player_id, season_id)
                VALUES (?, ?)
            """
            self._db.execute_update(query, (player_id, season_id))

    def update_season_score(self, player_id: str, season_id: int, **kwargs):
        """
        Update a player's season score with the provided field values.

        Example:
            update_season_score(player_id, season_id, points=150, correct_answers=3)
        """
        if not kwargs:
            return

        # Ensure record exists
        self.initialize_player_season_score(player_id, season_id)

        # Build UPDATE statement dynamically
        set_clauses = ", ".join(f"{key} = ?" for key in kwargs.keys())
        values = list(kwargs.values()) + [player_id, season_id]

        query = f"""
            UPDATE season_scores
            SET {set_clauses}
            WHERE player_id = ? AND season_id = ?
        """
        self._db.execute_update(query, tuple(values))

    def increment_season_stat(
        self, player_id: str, season_id: int, stat_name: str, amount: int = 1
    ):
        """Atomically increment a season stat."""
        self.initialize_player_season_score(player_id, season_id)

        query = f"""
            UPDATE season_scores
            SET {stat_name} = {stat_name} + ?
            WHERE player_id = ? AND season_id = ?
        """
        self._db.execute_update(query, (amount, player_id, season_id))

    def get_player_trophies(self, player_id: str):
        """
        Get all trophies won by a player across all seasons.

        Returns:
            List of dicts with season_name, trophy, and season_id
        """
        query = """
            SELECT s.season_name, ss.trophy, s.season_id
            FROM season_scores ss
            JOIN seasons s ON ss.season_id = s.season_id
            WHERE ss.player_id = ? AND ss.trophy IS NOT NULL
            ORDER BY s.start_date DESC
        """
        return self._db.execute_query(query, (player_id,))

    def get_trophy_counts(self, player_id: str) -> dict:
        """
        Get counts of each trophy type for a player.

        Returns:
            Dict like {"gold": 2, "silver": 1, "bronze": 3}
        """
        trophies = self.get_player_trophies(player_id)
        counts = {"gold": 0, "silver": 0, "bronze": 0}

        for trophy_record in trophies:
            trophy_type = trophy_record["trophy"]
            if trophy_type in counts:
                counts[trophy_type] += 1

        return counts

    def finalize_season_rankings(self, season_id: int):
        """
        Calculate and store final rankings for a season.
        Awards trophies to top performers.
        Handles ties: players with same score get same rank and trophy.
        """
        scores = self.get_season_scores(season_id, limit=1000)  # Get all

        # Determine rankings (with tie handling)
        prev_score = None
        current_rank = 1

        for i, season_score in enumerate(scores):
            # Handle ties - same score = same rank
            if prev_score is not None and season_score.points < prev_score:
                current_rank = i + 1

            # Assign rank
            season_score.final_rank = current_rank

            # Award trophies to top 3 ranks (multiple players can share)
            if current_rank == 1:
                season_score.trophy = "gold"
            elif current_rank == 2:
                season_score.trophy = "silver"
            elif current_rank == 3:
                season_score.trophy = "bronze"

            # Update database
            self.update_season_score(
                season_score.player_id,
                season_id,
                final_rank=season_score.final_rank,
                trophy=season_score.trophy,
            )

            prev_score = season_score.points

    def get_season_challenge(self, season_id: int):
        """Get the challenge for a specific season."""
        from src.core.season import SeasonChallenge

        query = "SELECT * FROM season_challenges WHERE season_id = ?"
        result = self._db.execute_query(query, (season_id,))
        if result:
            return SeasonChallenge.from_db_row(result[0])
        return None

    def create_season_challenge(
        self,
        season_id: int,
        challenge_name: str,
        description: str,
        badge_emoji: str,
        completion_criteria: dict,
    ) -> int:
        """Create a challenge for a season."""
        import json

        query = """
            INSERT INTO season_challenges
            (season_id, challenge_name, description, badge_emoji, completion_criteria)
            VALUES (?, ?, ?, ?, ?)
        """
        cursor = self._db.execute_update(
            query,
            (
                season_id,
                challenge_name,
                description,
                badge_emoji,
                json.dumps(completion_criteria),
            ),
        )
        return cursor.lastrowid

    def update_lifetime_stats(self, player_id: str, **kwargs):
        """
        Update lifetime stats for a player (score, lifetime_questions, etc.).

        Example:
            update_lifetime_stats(player_id, score=500, lifetime_questions=10)
        """
        if not kwargs:
            return

        # Build UPDATE statement dynamically
        set_clauses = ", ".join(f"{key} = ?" for key in kwargs.keys())
        values = list(kwargs.values()) + [player_id]

        query = f"""
            UPDATE players
            SET {set_clauses}
            WHERE id = ?
        """
        self._db.execute_update(query, tuple(values))

    def increment_lifetime_stat(self, player_id: str, stat_name: str, amount: int = 1):
        """Atomically increment a lifetime stat."""
        query = f"""
            UPDATE players
            SET {stat_name} = {stat_name} + ?
            WHERE id = ?
        """
        self._db.execute_update(query, (amount, player_id))

    def reset_all_player_season_scores(self):
        """
        Reset all players' season_score and answer_streak to 0.
        Called at the start of a new season.
        """
        self._db.execute_update(
            "UPDATE players SET season_score = 0, answer_streak = 0"
        )
