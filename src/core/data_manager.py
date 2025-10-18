from typing import Optional
from datetime import date
from db.database import Database
from data.readers.question import Question

class DataManager:
    """
    Handles all database interactions for the bot.
    """

    def __init__(self, db: "Database"):
        """
        Initializes the data manager, connecting to the database.
        """
        self.db = db

    # TODO: Add a method to initialize the database from main.py

    # TODO: Add a method to load all player data, replacing _load_players in players.py

    # TODO: Add a method to save all player data, replacing save_players in players.py

    # TODO: Add a method to adjust player scores, replacing the direct query in admin.py

    # TODO: Add a method to get all players, replacing read_players_into_dict in players.py

    def log_daily_question(self, question: Question):
        """
        Logs details about a daily question that was sent out.

        Args:
            question (Question): The question object.
        """
        # First, ensure the question exists in the 'questions' table
        question_query = (
            "SELECT id FROM questions WHERE question_hash = ?"
        )
        existing_question = self.db.execute_query(
            question_query, (str(question.id),)
        )

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
        daily_question_info = self.get_todays_daily_question()
        if daily_question_info:
            _, daily_question_id = daily_question_info
            return daily_question_id

        # Log the daily question event
        daily_question_query = (
            "INSERT INTO daily_questions (question_id, sent_at) VALUES (?, ?)"
        )
        _, daily_question_id = self.db.execute_update(
            daily_question_query, (question_id, date.today())
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
        Logs details about any message sent or received by the bot.
        """
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
        query = "SELECT id, name, score FROM players WHERE score > 0 ORDER BY score DESC"
        return self.db.execute_query(query)

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
            question=q_data['question_text'],
            answer=q_data['answer_text'],
            category=q_data['category'],
            clue_value=q_data['value'],
            data_source=q_data['source'],
            hint=q_data['hint_text']
        )

    def get_todays_daily_question(self) -> Optional[tuple[Question, int]]:
        """
        Retrieves today's daily question as a Question object and its ID.
        """
        today = date.today()
        query = "SELECT id, question_id FROM daily_questions WHERE sent_at = ?"
        daily_question_info = self.db.execute_query(query, (today,))
        
        if not daily_question_info:
            return None
        
        daily_question_info = daily_question_info[0]

        question = self.get_question_by_id(daily_question_info["question_id"])
        daily_question_id = daily_question_info["id"]
        
        if not question:
            return None

        return question, daily_question_id
