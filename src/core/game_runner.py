import csv
import os
import re

from enum import Enum
from src.cfg.players import read_players_into_dict
from src.core.subscriber import Subscriber
from src.core.logger import Logger
from data.readers.question_selector import QuestionSelector
from data.readers.question import Question





class GameRunner:
    """
    Base class to represent the game logic.
    Manages the subscribed players and interacts with the question selector.
    """

    def __init__(
        self,
        question_selector: QuestionSelector,
        logger: Logger,
    ):
        self.question_selector = question_selector
        self.logger = logger
        self.subscribed_contexts = Subscriber.get_all(self.logger.db)
        self.daily_q = None
        self.managers = {}

    def register_manager(self, name: str, manager_class):
        """
        Registers a manager class.
        """
        self.managers[name] = manager_class

    def enable_manager(self, name: str, **kwargs):
        """
        Enables a manager by creating an instance of its class.
        """
        if name in self.managers:
            self.managers[name] = self.managers[name](**kwargs)
            print(f"Manager '{name}' enabled.")
        else:
            print(f"Manager '{name}' not found.")

    def disable_manager(self, name: str):
        """
        Disables a manager.
        """
        if name in self.managers and self.managers[name] is not None:
            self.managers[name] = None
            print(f"Manager '{name}' disabled.")
        else:
            print(f"Manager '{name}' is not enabled or not found.")

    def set_daily_question(self):
        self.daily_q = self.question_selector.get_question_for_today()

    def add_subscriber(self, subscriber: Subscriber):
        subscriber.db_conn = self.logger.db
        subscriber.save()
        self.subscribed_contexts.add(subscriber)

    def remove_subscriber(self, subscriber: Subscriber):
        subscriber.delete()
        self.subscribed_contexts.discard(subscriber)

    def get_subscribed_users(self):
        return self.subscribed_contexts



    def handle_guess(self, player_id: int, player_name: str, guess: str) -> bool:
        """
        Handles the answer submitted by a player, logs it, and returns correctness. In POWERUP mode, also resolves bets and attack effects.

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
        self.logger.log_player_guess(
            player_id, player_name, self.daily_q.id, g, is_correct
        )

        # Resolve with active managers
        for manager in self.managers.values():
            if manager is not None:
                manager.on_guess(player_id, player_name, guess, is_correct)

        return is_correct

    def get_scores_leaderboard(self) -> str:
        """Computes and formats the leaderboard string."""
        player_scores = self.logger.get_player_scores()

        if not player_scores:
            return "No scores available yet."

        # Sort players by score
        sorted_players = sorted(
            player_scores, key=lambda item: item["score"], reverse=True
        )

        if not sorted_players:
            return "No scores available yet."

        response_content = "-- Player Scores --\n"
        for i, player in enumerate(sorted_players, 1):
            response_content += f"{i}. {player['name']}: {player['score']}\n"
        return response_content

    def get_player_history(self, player_id: int, player_name: str) -> str:
        """Computes and formats the history/metrics string for a given player."""
        history = self.logger.read_guess_history(user_id=player_id)
        metrics = self.logger.get_guess_metrics(
            history, self.question_selector.questions
        )

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
            mentions = " ".join(
                [f"<@{player_id}>" for player_id in player_ids_not_guessed]
            )

        hint_part = ""
        if self.daily_q.hint:
            hint_part = f"\nHint: ||**{self.daily_q.hint}**||"

        flavor_message = (
            "Friendly reminder to get your guesses in!\n"
            f"Today's question is:\n{self.format_question(self.daily_q)}"
            f"{hint_part}"
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
            "Good evening players!\n" f"Here is the answer to today's trivia question:"
        )
        answer_part = self.format_answer(self.daily_q)
        return f"{flavor_message}\n{answer_part}\n{player_answers}"

    # TODO: Add more game-specific logic, e.g., tracking scores,
    # handling guesses, etc. for different game modes.
    # Handle game state management.
