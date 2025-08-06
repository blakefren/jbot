import csv
import os

from enum import Enum
from bot.subscriber import Subscriber
from readers.question_selector import QuestionSelector

# Construct the absolute path to the project's root directory
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SUBSCRIBERS_FILE = os.path.join(PROJECT_ROOT, "cfg", "subscribers.csv")


class GameType(Enum):
    """
    Enum to represent different game modes.
    """

    SIMPLE = "simple"  # TODO: split out from BaseGame, or combine?
    POKER = "poker"  # TODO
    POWERUP = "powerup"  # TODO
    VEGAS = "vegas"  # TODO
    SOULSLIKE = "soulslike"  # TODO
    JEOPARDY = "jeopardy"  # TODO


class GameRunner:
    """
    Base class to represent the game logic.
    Manages the subscribed players and interacts with the question selector.
    """

    def __init__(
        self, question_selector: QuestionSelector, mode: GameType = GameType.SIMPLE
    ):
        self.question_selector = question_selector
        self.mode = mode
        self.subscribed_contexts = self._load_subscribers()

    def _load_subscribers(self):
        subscribers = set()
        try:
            with open(SUBSCRIBERS_FILE, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader)  # Skip header
                for row in reader:
                    subscribers.add(Subscriber.from_csv_row(row))
        except FileNotFoundError:
            pass  # No subscribers file yet
        return subscribers

    def _save_subscribers(self):
        try:
            with open(SUBSCRIBERS_FILE, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["id", "display_name", "is_channel"])
                for sub in self.subscribed_contexts:
                    writer.writerow(sub.to_csv_row())
        except Exception as e:
            print(f"Error saving subscribers: {e}")

    def add_subscriber(self, subscriber: Subscriber):
        self.subscribed_contexts.add(subscriber)
        self._save_subscribers()

    def remove_subscriber(self, subscriber: Subscriber):
        if subscriber in self.subscribed_contexts:
            self.subscribed_contexts.remove(subscriber)
            self._save_subscribers()

    def get_subscribed_users(self):
        return self.subscribed_contexts

    def change_mode(self, new_mode: GameType):
        """
        Change the game mode.

        Args:
            new_mode (str): The new mode to switch to.
        """
        self.mode = new_mode
        print(f"Game mode changed to: {self.mode}")

    def send_morning_message(self):
        """
        Sends the daily question to all subscribers.
        """
        question = self.question_selector.get_question_for_today()
        for subscriber in self.subscribed_contexts:
            print(
                f"Sending morning message to {subscriber.display_name}: {question.text}"
            )
            # TODO

    def send_evening_message(self):
        """
        Sends the daily answer to all subscribers.
        """
        question = self.question_selector.get_question_for_today()
        for subscriber in self.subscribed_contexts:
            print(
                f"Sending evening message to {subscriber.display_name}: {question.answer}"
            )
            # TODO

    def handle_guess(self, subscriber: Subscriber, guess: str):
        """
        Handles the answer submitted by a subscriber.

        Args:
            subscriber (Subscriber): The subscriber who answered.
            answer (str): The answer provided by the subscriber.
        """
        question = self.question_selector.get_question_for_today()
        if guess.lower() == question.answer.lower():
            pass
        # TODO

    def calculate_scores(self):
        """
        Calculates and returns the scores of all subscribers.
        """
        scores = {}
        for subscriber in self.subscribed_contexts:
            scores[subscriber.display_name] = subscriber.score
        # TODO

    # TODO: Add more game-specific logic, e.g., tracking scores,
    # handling guesses, etc. for different game modes.
    # Handle game state management.
