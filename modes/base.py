from enum import Enum
from bot.subscriber import Subscriber
from readers.question_selector import QuestionSelector


class GameType(Enum):
    """
    Enum to represent different game modes.
    """

    SIMPLE = "simple"
    SQUID_GAME = "squid_game"
    DARK_SOULS = "dark_souls"
    JEOPARDY = "jeopardy"
    RANDOM = "random"


class BaseGame:
    """
    Base class to represent the game logic.
    Manages the subscribed players and interacts with the question selector.
    """

    def __init__(self, question_selector: QuestionSelector, mode: str = "default"):
        self.question_selector = question_selector
        self.subscribed_contexts = set()
        self.mode = mode

    def add_subscriber(self, subscriber: Subscriber):
        self.subscribed_contexts.add(subscriber)

    def remove_subscriber(self, subscriber: Subscriber):
        if subscriber in self.subscribed_contexts:
            self.subscribed_contexts.remove(subscriber)

    def get_subscribed_users(self):
        return self.subscribed_contexts

    def change_mode(self, new_mode: str):
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
