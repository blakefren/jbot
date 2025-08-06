import logging
import os
import re

from readers.question import Question

CURRENT_DIR = os.path.dirname(__file__)
HISTORY_FILE_PATH = os.path.join(CURRENT_DIR, "history.log")
MESSAGING_FILE_PATH = os.path.join(CURRENT_DIR, "messaging.log")
GUESSES_FILE_PATH = os.path.join(CURRENT_DIR, "guesses.log")


class Logger:
    """
    A logging class for the Jeopardy! chatbot, designed to log events
    to specific files based on their type (history, messaging, or guesses).
    """

    def __init__(self):
        """
        Initializes the logger, setting up separate log files.
        """
        os.makedirs(CURRENT_DIR, exist_ok=True)  # Ensure log directory exists

        # --- Setup History Logger ---
        self.history_logger = logging.getLogger("history")
        self.history_logger.setLevel(logging.INFO)
        history_handler = logging.FileHandler(HISTORY_FILE_PATH)
        history_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )
        history_handler.setFormatter(history_formatter)
        if not self.history_logger.handlers:
            self.history_logger.addHandler(history_handler)
        self.history_logger.propagate = False

        # --- Setup Messaging Logger ---
        self.messaging_logger = logging.getLogger("messaging")
        self.messaging_logger.setLevel(logging.INFO)
        messaging_handler = logging.FileHandler(MESSAGING_FILE_PATH)
        messaging_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )
        messaging_handler.setFormatter(messaging_formatter)
        if not self.messaging_logger.handlers:
            self.messaging_logger.addHandler(messaging_handler)
        self.messaging_logger.propagate = False
        
        # --- Setup Guesses Logger ---
        self.guesses_logger = logging.getLogger("guesses")
        self.guesses_logger.setLevel(logging.INFO)
        guesses_handler = logging.FileHandler(GUESSES_FILE_PATH)
        # Use a structured, easily parsable format
        guesses_formatter = logging.Formatter(
            "%(asctime)s - %(message)s", datefmt='%Y-%m-%d %H:%M:%S'
        )
        guesses_handler.setFormatter(guesses_formatter)
        if not self.guesses_logger.handlers:
            self.guesses_logger.addHandler(guesses_handler)
        self.guesses_logger.propagate = False

        print(f"Logger initialized. Logs will be saved in '{CURRENT_DIR}'.")

    def log_daily_question(self, question: Question, sent_to_users):
        """
        Logs details about a daily Jeopardy! question that was sent out.

        Args:
            question (Question): container object for question details.
            sent_to_users (list): A list of user identifiers (e.g., phone numbers or Discord IDs)
                                  to whom the question was sent.
        """
        log_message = (
            f"Daily Question Sent - ID: {question.id}, Category: {question.category}, "
            f"Value: ${question.clue_value}, Question: '{question.question}', Answer: '{question.answer}', "
            f"Sent To: {', '.join(map(str, sent_to_users))}"
        )
        self.history_logger.info(log_message)
        print(f"[History Logged] {log_message}")

    def log_player_guess(self, player_id: str, player_name: str, question_id: str, guess: str, is_correct: bool):
        """
        Logs a player's guess for a question in a structured format.

        Args:
            player_id (str): The unique identifier for the player.
            player_name (str): The display name of the player.
            question_id (str): The unique identifier for the question.
            guess (str): The answer submitted by the player.
            is_correct (bool): Whether the guess was correct.
        """
        # Clean the guess to avoid breaking the log format
        cleaned_guess = guess.replace("'", "\\'").replace("\n", " ")
        log_message = (
            f"PlayerGuess - PlayerID: {player_id}, PlayerName: '{player_name}', "
            f"QuestionID: {question_id}, Guess: '{cleaned_guess}', Correct: {is_correct}"
        )
        self.guesses_logger.info(log_message)
        print(f"[Guess Logged] {log_message}")

    def log_messaging_event(
        self, direction, method, recipient_or_sender, content, status="success"
    ):
        """
        Logs details about any message sent or received by the bot.

        Args:
            direction (str): 'to' for outgoing messages, 'from' for incoming messages.
            method (str): The communication method (e.g., 'SMS', 'Discord').
            recipient_or_sender (str): The phone number or Discord ID of the recipient/sender.
            content (str): The content of the message.
            status (str): The status of the message (e.g., 'success', 'failed').
        """
        content = content.replace("\n", " ").strip()
        log_message = (
            f"Message Event - Direction: {direction}, Method: {method}, "
            f"{'Recipient' if direction == 'to' else 'Sender'}: {recipient_or_sender}, "
            f"Content: '{content}', Status: {status}"
        )
        self.messaging_logger.info(log_message)
        print(f"[Messaging Logged] {log_message}")

    def _deduplicate_guesses(self, guess_history: list[dict]) -> list[dict]:
        """
        Helper method to deduplicate a list of guess dictionaries, keeping only the most recent entry for each player and question.
        
        Args:
            guess_history (list[dict]): A list of guess dictionaries.
            
        Returns:
            list[dict]: A deduplicated list of guess dictionaries.
        """
        unique_guesses = {}
        for g in guess_history:
            q_id = g.get('QuestionID', -1)
            p_id = g.get('PlayerID', -1)
            unique_key = (q_id, p_id)
            
            if unique_key not in unique_guesses:
                unique_guesses[unique_key] = g
            else:
                guess_time_current = unique_guesses[unique_key].get('timestamp', None)
                guess_time_new = g.get('timestamp', None)
                if guess_time_new and guess_time_current and guess_time_new > guess_time_current:
                    unique_guesses[unique_key] = g
        return list(unique_guesses.values())

    def read_guess_history(self, user_id: int = -1) -> list[dict]:
        """
        Reads and parses the guess history log file.

        Args:
            user_id (optional): ID of a user to filter answers for. Otherwise, return full answer history.
        
        Returns:
            list[dict]: A list of dictionaries, where each dictionary represents a guess.
                        Returns an empty list if the file doesn't exist or an error occurs.
        """
        guess_history = []
        if not os.path.exists(GUESSES_FILE_PATH):
            print("Guess history file not found. Returning empty list.")
            return guess_history

        # Regex to parse the structured log entry
        log_pattern = re.compile(
            r"(?P<timestamp>[\d\- :]+) - PlayerGuess - PlayerID: (?P<PlayerID>\S+), PlayerName: '(?P<PlayerName>.*?)', "
            r"QuestionID: (?P<QuestionID>\S+), Guess: '(?P<Guess>.*?)', Correct: (?P<Correct>\S+)"
        )

        try:
            with open(GUESSES_FILE_PATH, "r") as f:
                for line in f:
                    match = log_pattern.match(line.strip())
                    if match:
                        guess_data = match.groupdict()
                        # Convert boolean string to actual boolean
                        guess_data['Correct'] = guess_data['Correct'] == 'True'
                        try:
                            guess_data['QuestionID'] = int(guess_data['QuestionID'])
                        except (ValueError, TypeError):
                            continue
                        guess_history.append(guess_data)
        except Exception as e:
            print(f"Error reading or parsing guess history: {e}")
        
        # Return deduplicated history if no user ID provided.
        guess_history = self._deduplicate_guesses(guess_history)
        if user_id == -1:
            return guess_history
        else:
            unique_guesses = [g for g in guess_history if int(g.get('PlayerID', -1)) == user_id]
            return unique_guesses
    
    def get_guess_metrics(self, history: list[dict], all_questions: list[Question]):
        """
        Calculates and returns a dictionary of metrics based on guess history.

        Args:
            history (list[dict]): A list of guess dictionaries, typically from read_guess_history.
            all_questions (list[Question]): A list of all available questions to get clue values.

        Returns:
            dict: A dictionary of metrics.
        """
        metrics = {
            "total_guesses": len(history),
            "unique_questions": len(set(g['QuestionID'] for g in history)),
            "global_correct_rate": 0,
            "global_score": 0,
            "players": {},
        }

        # Map question IDs to their values for scoring
        question_values = {q.id: int(q.clue_value) for q in all_questions}

        player_data = {}
        for guess in history:
            player_id = guess['PlayerID']
            is_correct = guess['Correct']
            question_id = guess['QuestionID']
            clue_value = question_values.get(question_id, 0)

            if player_id not in player_data:
                player_data[player_id] = {
                    "total_guesses": 0,
                    "correct_guesses": 0,
                    "score": 0,
                    "player_name": guess['PlayerName']
                }

            player_data[player_id]["total_guesses"] += 1
            if is_correct:
                player_data[player_id]["correct_guesses"] += 1
                player_data[player_id]["score"] += clue_value

        total_correct_guesses = 0
        for player_id, data in player_data.items():
            total_correct_guesses += data['correct_guesses']
            metrics['global_score'] += data['score']
            if data['total_guesses'] > 0:
                data['correct_rate'] = data['correct_guesses'] / data['total_guesses']
            else:
                data['correct_rate'] = 0
            metrics["players"][player_id] = data

        if metrics['total_guesses'] > 0:
            metrics['global_correct_rate'] = total_correct_guesses / metrics['total_guesses']
        else:
            metrics['global_correct_rate'] = 0
            
        return metrics


# --- Example Usage ---
if __name__ == "__main__":
    logger = Logger()
    
    q = Question(
        id="jeopardy_1234",
        question="This city is known as the 'Big Apple'.",
        answer="New York City",
        category="US CITIES",
        clue_value=400,
        data_source="local",
        metadata={"air_date": "2023-10-27"},
    )

    # Log a correct guess
    logger.log_player_guess(
        player_id="discord_user_123",
        player_name="PlayerOne",
        question_id=q.id,
        guess="New York City",
        is_correct=True
    )

    # Log an incorrect guess
    logger.log_player_guess(
        player_id="discord_user_456",
        player_name="PlayerTwo",
        question_id=q.id,
        guess="Chicago",
        is_correct=False
    )

    # Read the history
    print("\n--- Reading Guess History ---")
    history = logger.read_guess_history()
    for entry in history:
        print(entry)
