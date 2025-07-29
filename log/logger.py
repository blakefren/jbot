# TODO: log question history
# TODO: log message history

import logging
import os

from readers.question import Question

CURRENT_DIR = os.path.dirname(__file__)
HISTORY_FILE_PATH = os.path.join(CURRENT_DIR, "history.log")
MESSAGING_FILE_PATH = os.path.join(CURRENT_DIR, "messaging.log")


class Logger:
    """
    A logging class for the Jeopardy! chatbot, designed to log events
    to specific files based on their type (history or messaging).
    """

    def __init__(self):
        """
        Initializes the logger, setting up separate log files for history and messaging.
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
        # Prevent adding multiple handlers if the logger is re-initialized (e.g., in tests)
        if not self.history_logger.handlers:
            self.history_logger.addHandler(history_handler)
        self.history_logger.propagate = False  # Prevent logs from going to root logger

        # --- Setup Messaging Logger ---
        self.messaging_logger = logging.getLogger("messaging")
        self.messaging_logger.setLevel(logging.INFO)
        messaging_handler = logging.FileHandler(MESSAGING_FILE_PATH)
        messaging_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )
        messaging_handler.setFormatter(messaging_formatter)
        # Prevent adding multiple handlers
        if not self.messaging_logger.handlers:
            self.messaging_logger.addHandler(messaging_handler)
        self.messaging_logger.propagate = (
            False  # Prevent logs from going to root logger
        )

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
        log_message = (
            f"Message Event - Direction: {direction}, Method: {method}, "
            f"{'Recipient' if direction == 'to' else 'Sender'}: {recipient_or_sender}, "
            f"Content: '{content}', Status: {status}"
        )
        self.messaging_logger.info(log_message)
        print(f"[Messaging Logged] {log_message}")


# --- Example Usage ---
if __name__ == "__main__":
    # Create a logger instance
    logger = Logger()

    # Log a daily question event
    q = Question(
        question="What is the capital of France?",
        answer="Paris",
        category="Geography",
        clue_value=200,
        data_source="local",
        metadata={"air_date": "2023-10-01"},
    )
    logger.log_daily_question(q, sent_to_users=["+15551234567", "discord_user_id_123"])

    # Log an outgoing SMS message
    logger.log_messaging_event(
        direction="to",
        method="SMS",
        recipient_or_sender="+15551234567",
        content="Jeopardy! Question: What is the capital of France?",
    )

    # Log an incoming Discord message (e.g., a guess)
    logger.log_messaging_event(
        direction="from",
        method="Discord",
        recipient_or_sender="discord_user_id_456",
        content="!guess Paris",
    )

    # Log an outgoing Discord message (e.g., the answer)
    logger.log_messaging_event(
        direction="to",
        method="Discord",
        recipient_or_sender="discord_channel_id_789",
        content="Jeopardy! Answer: What is Paris?",
    )

    # You can check the 'log' directory for 'history.log' and 'messaging.log' files.
    print("\nCheck the 'log' directory for the generated log files.")
