import csv
import os
import re

from enum import Enum
from bot.subscriber import Subscriber
from log.logger import Logger
from readers.question_selector import QuestionSelector
from cfg.players import read_players_into_dict
from readers.question import Question

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
        self,
        question_selector: QuestionSelector,
        logger: Logger,
        mode: GameType = GameType.SIMPLE,
    ):
        self.question_selector = question_selector
        self.logger = logger
        self.mode = mode
        self.subscribed_contexts = self._load_subscribers()
        self.daily_q = None

    def set_daily_question(self):
        self.daily_q = self.question_selector.get_question_for_today()

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

    def handle_guess(self, player_id: int, player_name: str, guess: str) -> bool:
        """
        Handles the answer submitted by a player, logs it, and returns correctness.

        Args:
            player_id (int): The Discord ID of the player.
            player_name (str): The Discord display name of the player.
            guess (str): The player's guess.

        Returns:
            bool: True if the guess was correct, False otherwise.
        """
        if not self.daily_q:
            return False  # No active question

        g = guess.strip().lower()
        a = self.daily_q.answer.strip().lower()
        is_correct = re.search(g, a) is not None
        self.logger.log_player_guess(player_id, player_name, self.daily_q.id, g, is_correct)
        return is_correct

    def get_scores_leaderboard(self) -> str:
        """Computes and formats the leaderboard string."""
        history = self.logger.read_guess_history()
        metrics = self.logger.get_guess_metrics(history, self.question_selector.questions)
        players_data = metrics.get("players", {})

        if not players_data:
            return "No scores available yet."

        # Sort players by score
        sorted_players = sorted(
            players_data.items(), key=lambda item: item[1].get("score", 0), reverse=True
        )

        if not sorted_players:
            return "No scores available yet."

        response_content = "-- Player Scores --\n"
        for i, (user_id, data) in enumerate(sorted_players, 1):
            player_name = data.get('player_name', user_id)
            score = data.get('score', 0)
            response_content += f"{i}. {player_name}: {score}\n"
        return response_content

    def get_player_history(self, player_id: int, player_name: str) -> str:
        """Computes and formats the history/metrics string for a given player."""
        history = self.logger.read_guess_history(user_id=player_id)
        metrics = self.logger.get_guess_metrics(history, self.question_selector.questions)

        full_message = ""
        player_metrics = metrics["players"].get(str(player_id), None)
        if player_metrics:
            correct_rate = player_metrics.get("correct_rate", 0)
            player_part = (
                f"--Your stats, {player_name}-- \n"
                f"Total guesses: {player_metrics.get('guesses')}\n"
                f"Correct rate:  {correct_rate:.2f}\n"
                f"Score:         {player_metrics.get('score')}"
            )
            full_message += player_part

        global_correct_rate = metrics.get("global_correct_rate", 0)
        global_part = (
            f"\n\n--Global data--\n"
            f"Global guesses:   {metrics.get('total_guesses')}\n"
            f"Unique questions: {metrics.get('unique_questions')}\n"
            f"Correct rate:     {global_correct_rate:.2f}\n"
            f"Global score:     {metrics.get('global_score')}"
        )
        full_message += global_part
        return full_message

    def format_question(self, question: Question) -> str:
        """Internal helper method to format a trivia question."""
        return (
            f"**--- Question! ---**\n"
            f"Category: **{question.category}**\n"
            f"Value: **${question.clue_value}**\n"
            f"Question: **{question.question}**\n"
        )

    def format_answer(self, question: Question) -> str:
        """Internal helper method to format a trivia answer."""
        min_display_size = 15
        pad_size = max(min_display_size - len(question.answer), 0) // 2
        padded_answer = question.answer.center(len(question.answer) + pad_size * 2, " ")
        return f"Answer: ||**{padded_answer}**||\n"

    def get_morning_message_content(self) -> str:
        """Generates the text for the morning question announcement."""
        if not self.daily_q:
            return "No question available for today."
        return self.format_question(self.daily_q)

    def get_reminder_message_content(self, tag_unanswered: bool) -> str:
        """Generates the reminder message, including tagging players who haven't answered."""
        if not self.daily_q:
            return "No question to remind about."

        # Get players who have guessed
        all_guesses = self.logger.read_guess_history()
        daily_guesses = [
            g for g in all_guesses if g.get("QuestionID") == self.daily_q.id
        ]
        player_ids_who_guessed = {g.get("PlayerID") for g in daily_guesses}

        # Get all players
        all_players = read_players_into_dict()
        player_ids_all = set(all_players.keys())

        # Find players who haven't guessed
        player_ids_not_guessed = player_ids_all - player_ids_who_guessed

        # Create the @mentions string
        mentions = ""
        if tag_unanswered and player_ids_not_guessed:
            mentions = " ".join([f"<@{player_id}>" for player_id in player_ids_not_guessed])

        flavor_message = (
            "Friendly reminder to get your guesses in!\n"
            f"Today's question is:\n{self.format_question(self.daily_q)}"
        )
        return f"{flavor_message}\n{mentions}"

    def get_evening_message_content(self) -> str:
        """Generates the evening message with the answer and a summary of player guesses."""
        if not self.daily_q:
            return "No question to answer for today."

        # Get all guesses for the daily question
        all_guesses = self.logger.read_guess_history()
        daily_guesses = [
            g for g in all_guesses if g.get("QuestionID") == self.daily_q.id
        ]

        player_answers = ""
        if daily_guesses:
            player_answers += "--Player answers--\n"
            for guess in daily_guesses:
                player_answers += f"{guess['PlayerName']}: {guess['Guess']}\n"

        flavor_message = (
            "Good evening players!\n"
            f"Here is the answer to today's trivia question:"
        )
        answer_part = self.format_answer(self.daily_q)
        return f"{flavor_message}\n{answer_part}\n{player_answers}"

    # TODO: Add more game-specific logic, e.g., tracking scores,
    # handling guesses, etc. for different game modes.
    # Handle game state management.
