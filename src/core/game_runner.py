import csv
import os
import re

from collections import defaultdict
from datetime import date
from enum import Enum
from src.cfg.players import PlayerManager
from src.core.subscriber import Subscriber
import logging
from src.core.data_manager import DataManager
from data.readers.question_selector import QuestionSelector
from data.readers.question import Question


class AlreadyAnsweredCorrectlyError(Exception):
    """Raised when a player tries to answer a question they have already answered correctly."""
    pass


class GameRunner:
    """
    Base class to represent the game logic.
    Manages the subscribed players and interacts with the question selector.
    """

    def __init__(
        self,
        question_selector: QuestionSelector,
        data_manager: DataManager,
    ):
        self.question_selector = question_selector
        self.data_manager = data_manager
        self.player_manager = PlayerManager(self.data_manager.db)
        self.subscribed_contexts = Subscriber.get_all(self.data_manager.db)
        self.daily_q = None
        self.daily_question_id = None
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
            logging.info(f"Manager '{name}' enabled.")
        else:
            logging.warning(f"Manager '{name}' not found.")

    def disable_manager(self, name: str):
        """
        Disables a manager.
        """
        if name in self.managers and self.managers[name] is not None:
            self.managers[name] = None
            logging.info(f"Manager '{name}' disabled.")
        else:
            logging.warning(f"Manager '{name}' is not enabled or not found.")

    def set_daily_question(self):
        logging.debug(f"GameRunner.set_daily_question.")
        
        # Check for an existing daily question ID for today
        daily_question_data = self.data_manager.get_todays_daily_question()
        if daily_question_data:
            self.daily_q, self.daily_question_id = daily_question_data
            logging.info(f"Daily question already set with ID: {self.daily_question_id}")
            return

        # Otherwise, select a new question
        self.daily_q = self.question_selector.get_question_for_today()
        if self.daily_q:
            self.daily_question_id = self.data_manager.log_daily_question(self.daily_q)
            if self.daily_question_id is None:
                # If log_daily_question returns None, it means a question for today already exists.
                # We need to get the ID of that existing question.
                daily_question_data = self.data_manager.get_todays_daily_question()
                if daily_question_data:
                    self.daily_question_id = daily_question_data[1]
            logging.info(f"Daily question set with ID: {self.daily_question_id}")

    def add_subscriber(self, subscriber: Subscriber):
        subscriber.db_conn = self.data_manager.db
        subscriber.save()
        self.subscribed_contexts.add(subscriber)

    def remove_subscriber(self, subscriber: Subscriber):
        subscriber.delete()
        self.subscribed_contexts.discard(subscriber)

    def get_subscribed_users(self):
        return self.subscribed_contexts

    def _is_correct_guess(self, guess: str, answer: str) -> bool:
        """
        Internal helper method to determine if a guess matches the answer.
        Currently uses simple substring matching (case insensitive).
        """
        # TODO: Improve matching logic (e.g., fuzzy matching, ignore punctuation, etc.)
        return re.search(guess, answer) is not None

    def get_player_guesses(self, player_id: int) -> list:
        """
        Returns all guesses for the current daily question for the given player.
        """
        if not self.daily_question_id:
            return []
        guesses = self.data_manager.read_guess_history(user_id=player_id)
        # Only include guesses for the current daily question
        return [g.get("guess_text") for g in guesses if g.get("daily_question_id") == self.daily_question_id]

    def has_answered_correctly_today(self, player_id: int) -> bool:
        """
        Checks if the player has already answered today's question correctly.
        """
        if not self.daily_question_id:
            return False
        
        guesses = self.data_manager.read_guess_history(user_id=player_id)
        for guess in guesses:
            if guess.get("daily_question_id") == self.daily_question_id and guess.get("is_correct"):
                return True
        return False


    def handle_guess(self, player_id: int, player_name: str, guess: str) -> tuple[bool, int]:
        """
        Handles the answer submitted by a player, logs it, and returns correctness.

        Args:
            player_id (int): The Discord ID of the player.
            player_name (str): The Discord display name of the player.
            guess (str): The player's guess.

        Returns:
            tuple[bool, int]: A tuple containing:
                - bool: True if the guess was correct, False otherwise.
                - int: The number of guesses the player has made for this question.
        
        Raises:
            AlreadyAnsweredCorrectlyError: If the player has already answered correctly.
        """
        if not self.daily_q:
            return False, 0  # No active question

        # Check if the player has already answered correctly today
        if self.has_answered_correctly_today(player_id):
            raise AlreadyAnsweredCorrectlyError()

        # Get the number of guesses for this question
        num_guesses = len(self.get_player_guesses(player_id)) + 1

        g = guess.strip().lower()
        a = str(self.daily_q.answer).strip().lower()
        is_correct = self._is_correct_guess(g, a)
        self.data_manager.log_player_guess(
            player_id, player_name, self.daily_question_id, g, is_correct
        )
        logging.info(f"Player {player_name} guessed '{g}'. Correct: {is_correct}")

        # Resolve with active managers
        for manager in self.managers.values():
            if manager is not None and not isinstance(manager, type):
                try:
                    manager.on_guess(player_id, player_name, guess, is_correct)
                except TypeError as e:
                    logging.error(f"Error calling on_guess for {type(manager).__name__}: {e}")
                    # Attempt to call with fewer arguments for backward compatibility
                    try:
                        manager.on_guess(player_id, is_correct)
                    except TypeError:
                        pass  # Or log that this also failed

        return is_correct, num_guesses

    def get_scores_leaderboard(self, guild=None) -> str:
        """Computes and formats the leaderboard string."""
        player_scores = self.data_manager.get_player_scores()

        if not player_scores:
            return "No scores available yet."

        scores_by_points = defaultdict(list)
        for player in player_scores:
            player_name = player["name"]
            if guild:
                try:
                    member = guild.get_member(int(player["id"]))
                    if member:
                        player_name = member.nick if member.nick else member.display_name
                except Exception as e:
                    logging.warning(f"Could not resolve player name for {player['id']}: {e}")
            scores_by_points[player['score']].append(player_name)

        if not scores_by_points:
            return "No scores available yet."

        # Sort scores in descending order
        sorted_scores = sorted(scores_by_points.keys(), reverse=True)

        response_content = "-- Player Scores --\n"
        for score in sorted_scores:
            # Sort player names alphabetically
            sorted_names = sorted(scores_by_points[score])
            response_content += f"{score}: {', '.join(sorted_names)}\n"
        return response_content

    def get_player_history(self, player_id: int, player_name: str) -> str:
        """Computes and formats the history/metrics string for a given player."""
        history = self.data_manager.read_guess_history(user_id=player_id)
        if not history:
            return f"No history found for {player_name}."

        total_guesses = len(history)
        correct_guesses = sum(1 for g in history if g['is_correct'])
        correct_rate = (correct_guesses / total_guesses) * 100 if total_guesses > 0 else 0

        player = self.player_manager.get_player(str(player_id))
        score = player.score if player else 0

        return (
            f"-- Your stats, {player_name} --\n"
            f"Total guesses: {total_guesses}\n"
            f"Correct rate:  {correct_rate:.2f}%\n"
            f"Score:         {score}"
        )

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
        all_guesses = self.data_manager.read_guess_history()
        daily_guesses = [
            g for g in all_guesses if g.get("daily_question_id") == self.daily_question_id
        ]
        player_ids_who_guessed = {g.get("player_id") for g in daily_guesses}

        # Get all players
        all_players = self.player_manager.get_all_players()
        player_ids_all = set(int(k) for k in all_players.keys())

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

    def get_evening_message_content(self, guild=None) -> str:
        """Generates the evening message with the answer and a summary of player guesses, using server nicknames if possible."""
        if not self.daily_q:
            return "No question to answer for today."

        # Get all guesses for the daily question
        all_guesses = self.data_manager.read_guess_history()
        daily_guesses = [
            g for g in all_guesses if g.get("daily_question_id") == self.daily_question_id
        ]

        player_answers = ""
        if daily_guesses:
            player_guesses_map = defaultdict(list)
            for g in daily_guesses:
                player_guesses_map[g['player_id']].append(g)

            player_display_list = []

            for player_id, guesses in player_guesses_map.items():
                # Deduplicate guesses for each player, keeping track of correctness
                unique_guesses = {g['guess_text']: g['is_correct'] for g in guesses}

                formatted_guesses = []
                # Sort by guess text
                for guess_text, is_correct in sorted(unique_guesses.items()):
                    if is_correct:
                        formatted_guesses.append(f"**{guess_text}**")
                    else:
                        formatted_guesses.append(guess_text)

                # Resolve player name using guild nickname if possible
                player_name = guesses[0]['player_name']
                if guild:
                    try:
                        member = guild.get_member(int(player_id))
                        if member:
                            player_name = member.nick if member.nick else member.display_name
                    except Exception as e:
                        logging.warning(f"Could not resolve player name for {player_id}: {e}")

                player_display_list.append((player_name, ", ".join(formatted_guesses)))

            # Sort by player name
            player_display_list.sort()

            player_answers += "--Player answers--\n"
            for player_name, formatted_guesses_str in player_display_list:
                player_answers += f"**{player_name}**: {formatted_guesses_str}\n"

        flavor_message = (
            "Good evening players!\n" f"Here is the answer to today's trivia question:"
        )
        answer_part = self.format_answer(self.daily_q)
        return f"{flavor_message}\n{answer_part}\n{player_answers}"

    def update_scores(self):
        """
        Finalizes and saves player scores for the day.
        """
        if not self.daily_question_id:
            logging.warning("No daily question ID set, cannot update scores.")
            return

        # Get all correct guesses for the daily question
        all_guesses = self.data_manager.read_guess_history()
        correct_guesses = [
            g for g in all_guesses 
            if g.get("daily_question_id") == self.daily_question_id and g.get("is_correct")
        ]

        # Get unique players who answered correctly
        players_answered_correctly = {g['player_id']: g.get('player_name', 'Unknown') for g in correct_guesses}

        for player_id, player_name in players_answered_correctly.items():
            player = self.player_manager.get_or_create_player(str(player_id), player_name)
            if player:
                try:
                    player.update_score(self.daily_q.clue_value)
                except (TypeError, AttributeError):
                    player.update_score(100)
        
        self.player_manager.save_players()
        logging.info("Player scores updated and saved.")

    # TODO: Implement score adjustment logic from admin cog
    def adjust_score(self, player_id: int, amount: int, reason: str):
        """
        Adjusts a player's score by a given amount.
        """
        pass

    # TODO: Implement powerup logic from powerup manager
    def reinforce(self, player1_id: str, player2_id: str):
        pass

    def resolve_reinforce(self, player_id: str, correct: bool):
        pass

    def steal(self, thief_id: str, target_id: str):
        pass

    def disrupt(self, attacker_id: str, target_id: str):
        pass

    def use_shield(self, player_id: str):
        pass

    def place_wager(self, player_id: str, amount: int):
        pass

    def resolve_wager(self, player_id: str, correct: bool):
        pass
