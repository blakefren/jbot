import csv
import os
import re
import wcwidth

from collections import defaultdict
from datetime import date, datetime
from enum import Enum
from src.core.player_manager import PlayerManager
from src.core.subscriber import Subscriber
import logging
from src.core.data_manager import DataManager
from data.readers.question_selector import QuestionSelector
from data.readers.question import Question
from src.core.guess_handler import GuessHandler
from src.cfg.main import ConfigReader


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
        self.player_manager = PlayerManager(self.data_manager)
        self.subscribed_contexts = self.data_manager.get_all_subscribers()
        self.daily_q = None
        self.daily_question_id = None
        self.managers = {}
        self.config = ConfigReader()
        self.reminder_time = None

        # Feature flags
        self.features = {
            "fight": self.config.get_bool("JBOT_ENABLE_FIGHT", False),
            "powerup": self.config.get_bool("JBOT_ENABLE_POWERUP", False),
            "coop": self.config.get_bool("JBOT_ENABLE_COOP", False),
        }

        # Initialize PowerUpManager if any related feature is enabled
        if any(self.features.values()):
            from src.core.powerup import PowerUpManager

            self.managers["powerup"] = PowerUpManager(self.player_manager)
            logging.info(f"PowerUpManager enabled with features: {self.features}")

    def _get_valid_question(self) -> Question:
        """
        Helper method to find a valid question, retrying if necessary.
        Logs invalid questions as used.
        """
        used_hashes = self.data_manager.get_used_question_hashes()
        retries = int(self.config.get("JBOT_QUESTION_RETRIES", 10))

        for _ in range(retries):
            question = self.question_selector.get_random_question(
                exclude_hashes=used_hashes
            )

            if not question:
                logging.warning("No questions available.")
                return None

            if not question.is_valid:
                logging.info(f"Skipping invalid question: {question.question}")
                # Log it as used so we don't pick it again
                # Append (Invalid) to source to distinguish in DB
                question.data_source += " (Invalid)"
                self.data_manager.log_daily_question(question, mark_as_used_only=True)
                used_hashes.add(str(question.id))
                continue

            return question

        logging.warning(f"Could not find a valid question after {retries} attempts.")
        return None

    def reset_daily_question(self):
        """
        Resets the daily question by selecting a new one.
        This is intended for admin use to skip a problematic or unwanted question.
        """
        logging.info("Admin triggered reset of daily question.")

        self.daily_q = self._get_valid_question()

        if self.daily_q and self.daily_q.is_valid:
            # Invalidate the old question by logging the new one for today.
            # The DB schema ensures only one question per day, so this will either
            # fail if not set up correctly, or overwrite/ignore.
            # `log_daily_question` should ideally handle this.
            # For now, we assume it replaces or the logic inside handles it.
            self.daily_question_id = self.data_manager.log_daily_question(
                self.daily_q, force_new=True
            )
            if self.daily_question_id is None:
                logging.error("Failed to log new daily question during reset.")
                return False
            logging.info(f"Daily question reset to new ID: {self.daily_question_id}")
            return True
        return False

    def set_daily_question(self):
        logging.debug(f"GameRunner.set_daily_question.")

        # Check for an existing daily question ID for today
        daily_question_data = self.data_manager.get_todays_daily_question()
        if daily_question_data:
            self.daily_q, self.daily_question_id = daily_question_data
            logging.info(
                f"Daily question already set with ID: {self.daily_question_id}"
            )
            return

        # Otherwise, select a new question
        self.daily_q = self._get_valid_question()

        if self.daily_q and self.daily_q.is_valid:
            # If the question has no hint, try to generate one.
            if not self.daily_q.hint:
                logging.info(
                    f"Question {self.daily_q.id} is missing a hint. Generating one..."
                )
                try:
                    new_hint = self.question_selector.get_hint_from_gemini(self.daily_q)
                    if new_hint:
                        self.daily_q.hint = new_hint
                        logging.info(
                            f"Successfully generated hint for question {self.daily_q.id}."
                        )
                except Exception as e:
                    logging.error(
                        f"Error generating hint for question {self.daily_q.id}: {e}"
                    )

            self.daily_question_id = self.data_manager.log_daily_question(self.daily_q)
            if self.daily_question_id is None:
                # If log_daily_question returns None, it means a question for today already exists.
                # We need to get the ID of that existing question.
                daily_question_data = self.data_manager.get_todays_daily_question()
                if daily_question_data:
                    self.daily_question_id = daily_question_data[1]
            logging.info(f"Daily question set with ID: {self.daily_question_id}")

    def add_subscriber(self, subscriber: Subscriber):
        self.data_manager.save_subscriber(subscriber)
        self.subscribed_contexts.add(subscriber)

    def remove_subscriber(self, subscriber: Subscriber):
        self.data_manager.delete_subscriber(subscriber)
        self.subscribed_contexts.discard(subscriber)

    def get_subscribed_users(self):
        return self.subscribed_contexts

    def handle_guess(
        self, player_id: int, player_name: str, guess: str
    ) -> tuple[bool, int, int, list[str]]:
        """
        Handles the answer submitted by a player by delegating to GuessHandler.

        Args:
            player_id (int): The Discord ID of the player.
            player_name (str): The Discord display name of the player.
            guess (str): The player's guess.

        Returns:
            tuple: (is_correct, num_guesses, points_earned, bonus_messages)

        Raises:
            AlreadyAnsweredCorrectlyError: If the player has already answered correctly.
        """
        if not self.daily_q:
            return False, 0, 0, []  # No active question

        guess_handler = GuessHandler(
            self.data_manager,
            self.player_manager,
            self.daily_q,
            self.daily_question_id,
            self.managers,
            reminder_time=self.reminder_time,
        )
        return guess_handler.handle_guess(player_id, player_name, guess)

    def get_scores_leaderboard(self, guild=None, show_daily_bonuses=False) -> str:
        """Computes and formats the leaderboard string."""
        player_scores = self.data_manager.get_player_scores()

        if not player_scores:
            return "No scores available yet."

        streaks = {
            s["id"]: s["answer_streak"] for s in self.data_manager.get_player_streaks()
        }

        # Get daily bonuses if requested
        fastest_guesser_id = None
        first_try_solver_ids = set()
        before_hint_solver_ids = set()

        if show_daily_bonuses and self.daily_question_id:
            all_guesses = self.data_manager.read_guess_history()
            daily_correct_guesses = [
                g
                for g in all_guesses
                if g.get("daily_question_id") == self.daily_question_id
                and g.get("is_correct")
            ]
            # Sort by guessed_at to determine order
            daily_correct_guesses.sort(key=lambda x: x.get("guessed_at"))

            if daily_correct_guesses:
                fastest_guesser_id = daily_correct_guesses[0]["player_id"]

            # Check for before hint solvers
            hint_timestamp_str = self.data_manager.get_hint_sent_timestamp(
                self.daily_question_id
            )

            for g in daily_correct_guesses:
                if hint_timestamp_str:
                    if g.get("guessed_at") < hint_timestamp_str:
                        before_hint_solver_ids.add(g["player_id"])
                else:
                    # If hint hasn't been sent, everyone is before hint
                    before_hint_solver_ids.add(g["player_id"])

            first_try_solvers = self.data_manager.get_first_try_solvers(
                self.daily_question_id
            )
            first_try_solver_ids = {p["id"] for p in first_try_solvers}

        emoji_fastest = self.config.get("JBOT_EMOJI_FASTEST", "🥇")
        emoji_first_try = self.config.get("JBOT_EMOJI_FIRST_TRY", "🎯")
        emoji_before_hint = self.config.get("JBOT_EMOJI_BEFORE_HINT", "🧠")
        emoji_streak = self.config.get("JBOT_EMOJI_STREAK", "🔥")

        # Create a list of player data
        all_player_data = []
        for player in player_scores:
            player_id = player["id"]
            player_name = player["name"]
            if guild:
                try:
                    member = guild.get_member(int(player_id))
                    if member:
                        player_name = (
                            member.nick if member.nick else member.display_name
                        )
                except Exception as e:
                    logging.warning(
                        f"Could not resolve player name for {player_id}: {e}"
                    )

            streak = streaks.get(player_id, 0)
            score = player["score"]

            badges = []
            if streak > 0:
                badges.append(f"{streak}{emoji_streak}")

            if show_daily_bonuses:
                if player_id in first_try_solver_ids:
                    badges.append(emoji_first_try)
                if player_id in before_hint_solver_ids:
                    badges.append(emoji_before_hint)
                if player_id == fastest_guesser_id:
                    badges.append(emoji_fastest)

            badges_str = "".join(badges)

            all_player_data.append(
                {"name": player_name, "score": score, "badges": badges_str}
            )

        # Sort players by score (desc), then by name (asc)
        all_player_data.sort(key=lambda p: (-p["score"], p["name"]))

        # Determine column widths
        max_name = (
            max(len(p["name"]) for p in all_player_data) if all_player_data else 10
        )
        max_score = max(
            5,  # Num chars in "score" header
            (
                max(len(str(p["score"])) for p in all_player_data)
                if all_player_data
                else 0
            ),
        )
        max_badges = max(
            6,  # Num chars in "Badges" header
            (
                max(wcwidth.wcswidth(p["badges"]) for p in all_player_data)
                if all_player_data
                else 0
            ),
        )

        # Header
        header = f"{'Rank'} {'Player':<{max_name}} {'Score':<{max_score}}"
        header += f" {'Badges' if show_daily_bonuses else 'Streak'}"
        header += "\n"

        divider = f"{'-'*4} {'-'*max_name} {'-'*max_score}"
        divider += f" {'-'*max_badges}"
        divider += "\n"

        # Body
        body = ""
        rank = 0
        last_score = -1
        for i, p_data in enumerate(all_player_data):
            # Handle rank ties
            if p_data["score"] < last_score:
                rank = i + 1
            elif last_score == -1:
                rank = 1

            name = p_data["name"]
            score = p_data["score"]
            badges = p_data["badges"]

            # For ties, only show rank and score for the first player
            if p_data["score"] == last_score:
                body += f"{'':>4} {name:<{max_name}} {'':>{max_score}}"
            else:
                body += f"{rank:>4} {name:<{max_name}} {score:>{max_score}}"

            body += f" {badges}"

            body += "\n"

            last_score = p_data["score"]
        return f"```{header}{divider}{body}```"

    def get_player_history(self, player_id: int, player_name: str) -> str:
        """Computes and formats the history/metrics string for a given player."""
        history = self.data_manager.read_guess_history(user_id=player_id)
        if not history:
            return f"No history found for {player_name}."

        total_guesses = len(history)
        correct_guesses = sum(1 for g in history if g["is_correct"])
        correct_rate = (
            (correct_guesses / total_guesses) * 100 if total_guesses > 0 else 0
        )

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
            g
            for g in all_guesses
            if g.get("daily_question_id") == self.daily_question_id
        ]
        player_ids_who_guessed = {g.get("player_id") for g in daily_guesses}

        # Get all players
        all_players = self.player_manager.get_all_players()
        player_ids_all = set(k for k in all_players.keys())

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
            g
            for g in all_guesses
            if g.get("daily_question_id") == self.daily_question_id
        ]

        player_answers = ""
        if daily_guesses:
            player_guesses_map = defaultdict(list)
            for g in daily_guesses:
                player_guesses_map[g["player_id"]].append(g)

            player_display_list = []

            for player_id, guesses in player_guesses_map.items():
                # Deduplicate guesses for each player, keeping track of correctness
                unique_guesses = {g["guess_text"]: g["is_correct"] for g in guesses}

                formatted_guesses = []
                # Sort by guess text
                for guess_text, is_correct in sorted(unique_guesses.items()):
                    if is_correct:
                        formatted_guesses.append(f"**{guess_text}**")
                    else:
                        formatted_guesses.append(guess_text)

                # Resolve player name using guild nickname if possible
                player_name = guesses[0]["player_name"]
                if guild:
                    try:
                        member = guild.get_member(int(player_id))
                        if member:
                            player_name = (
                                member.nick if member.nick else member.display_name
                            )
                    except Exception as e:
                        logging.warning(
                            f"Could not resolve player name for {player_id}: {e}"
                        )

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
