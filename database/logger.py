import os
from datetime import date
from database.database import Database
from bot.readers.question import Question


class Logger:
    """
    A logging class for the trivia bot, designed to log events to a SQLite database.
    """

    def __init__(self, db_path: str):
        """
        Initializes the logger, connecting to the database.
        """
        self.db = Database(db_path)
        print(f"Logger initialized. Using database at '{db_path}'.")

    def close(self):
        """
        Closes the database connection.
        """
        self.db.close()
        print("Logger database connection closed.")

    def log_daily_question(self, question: Question, sent_to_users):
        """
        Logs details about a daily question that was sent out.

        Args:
            question (Question): The question object.
            sent_to_users (list): A list of user identifiers.
        """
        # First, ensure the question exists in the 'questions' table
        question_query = (
            "SELECT id FROM questions WHERE question_text = ? AND answer_text = ?"
        )
        existing_question = self.db.execute_query(
            question_query, (question.question, question.answer)
        )

        if existing_question:
            question_id = existing_question[0]["id"]
        else:
            # Insert the new question and get its ID
            # TODO: insert hint as well
            insert_query = """
                INSERT INTO questions (question_text, answer_text, category, value, source)
                VALUES (?, ?, ?, ?, ?)
            """
            self.db.execute_update(
                insert_query,
                (
                    question.question,
                    question.answer,
                    question.category,
                    question.clue_value,
                    question.data_source,
                ),
            )
            question_id = self.db.execute_query("SELECT last_insert_rowid() as id")[0][
                "id"
            ]

        # Log the daily question event
        daily_question_query = (
            "INSERT INTO daily_questions (question_id, sent_at) VALUES (?, ?)"
        )
        self.db.execute_update(daily_question_query, (question_id, date.today()))

        print(f"[History Logged] Daily Question Sent - ID: {question_id}")

    def log_player_guess(
        self,
        player_id: str,
        player_name: str,
        question_id: str,  # This should now be the daily_question_id
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
        print(
            f"[Guess Logged] Player {player_name} guessed '{guess}' for question {question_id}. Correct: {is_correct}"
        )

    def log_messaging_event(
        self, direction, method, recipient_or_sender, content, status="success"
    ):
        """
        Logs details about any message sent or received by the bot.
        """
        query = """
            INSERT INTO messages (direction, method, recipient_sender, content, status)
            VALUES (?, ?, ?, ?, ?)
        """
        self.db.execute_update(
            query, (direction, method, recipient_or_sender, content, status)
        )
        print(
            f"[Messaging Logged] {direction} message via {method} to/from {recipient_or_sender}"
        )

    def read_guess_history(self, user_id: int = -1) -> list[dict]:
        """
        Reads and parses the guess history from the database.
        """
        query = "SELECT * FROM guesses"
        params = ()
        if user_id != -1:
            query += " WHERE player_id = ?"
            params = (user_id,)

        return self.db.execute_query(query, params)

    def get_guess_metrics(self, all_questions: list[Question]):
        """
        Calculates and returns a dictionary of metrics based on guess history from the database.
        """
        # This method would need to be significantly reworked to pull from the DB
        # For now, we'll return a placeholder. A full implementation would require
        # more complex queries joining a few of the tables.
        print("get_guess_metrics needs to be refactored for database use.")
        return {}


# --- Example Usage ---
if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "database", "jbot.db")
    logger = Logger(db_path=db_path)

    q = Question(
        id="jeopardy_1234",
        question="This city is known as the 'Big Apple'.",
        answer="New York City",
        category="US CITIES",
        clue_value=400,
        data_source="local",
        metadata={"air_date": "2023-10-27"},
    )

    # Log a daily question
    logger.log_daily_question(q, ["user1", "user2"])

    # Get the ID of the daily question we just logged
    daily_question_id = logger.db.execute_query(
        "SELECT id FROM daily_questions ORDER BY id DESC LIMIT 1"
    )[0]["id"]

    # Log a correct guess
    logger.log_player_guess(
        player_id="discord_user_123",
        player_name="PlayerOne",
        question_id=daily_question_id,
        guess="New York City",
        is_correct=True,
    )

    # Log an incorrect guess
    logger.log_player_guess(
        player_id="discord_user_456",
        player_name="PlayerTwo",
        question_id=daily_question_id,
        guess="Chicago",
        is_correct=False,
    )

    # Read the history
    print("\n--- Reading Guess History ---")
    history = logger.read_guess_history()
    for entry in history:
        print(entry)

    logger.close()
