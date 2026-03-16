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
from src.core.powerup import PowerUpManager
from data.readers.question_selector import QuestionSelector
from data.readers.question import Question
from src.core.guess_handler import GuessHandler
from src.cfg.main import ConfigReader
from src.core.daily_game_simulator import DailyGameSimulator
from src.core.events import GuessEvent, PowerUpEvent
from src.core.answer_checker import AnswerChecker


class GameRunner:
    """
    Base class to represent the game logic.
    Manages the subscribed players and interacts with the question selector.
    """

    def __init__(
        self,
        question_selector: QuestionSelector,
        data_manager: DataManager,
        player_manager: PlayerManager = None,
    ):
        self.question_selector = question_selector
        self.data_manager = data_manager
        self.player_manager = player_manager or PlayerManager(self.data_manager)
        self.subscribed_contexts = self.data_manager.get_all_subscribers()
        self.daily_q = None
        self.daily_question_id = None
        self.question_db_id = None  # Database ID from questions table
        self.managers = {}
        self.config = ConfigReader()
        self.reminder_time = None

        # Feature flags
        self.features = {
            "fight": self.config.get_bool("JBOT_ENABLE_FIGHT"),
        }

        # Initialize PowerUpManager (always enabled)
        self.managers["powerup"] = PowerUpManager(
            self.player_manager, self.data_manager
        )
        logging.info(f"PowerUpManager enabled. Features: {self.features}")

    def _get_valid_question(self) -> Question:
        """
        Helper method to find a valid question, retrying if necessary.
        Logs invalid questions as used.
        """
        used_hashes = self.data_manager.get_used_question_hashes()
        # Fetch configured days of answers to avoid duplicates in AI generation
        history_days = int(self.config.get("JBOT_RIDDLE_HISTORY_DAYS"))
        recent_answers = self.data_manager.get_recent_answers(limit=history_days)

        retries = int(self.config.get("JBOT_QUESTION_RETRIES"))

        for _ in range(retries):
            question = self.question_selector.get_random_question(
                exclude_hashes=used_hashes, previous_answers=recent_answers
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
        """
        Sets the daily question for today, generating a hint if needed.

        Note: Hint generation can block for 10+ seconds. Future improvement:
        make this async to prevent blocking Discord's event loop.
        """
        logging.debug(f"GameRunner.set_daily_question.")

        # Check for an existing daily question ID for today
        daily_question_data = self.data_manager.get_todays_daily_question()
        if daily_question_data:
            self.daily_q, self.daily_question_id, self.question_db_id = (
                daily_question_data
            )
            logging.info(
                f"Daily question already set with ID: {self.daily_question_id}"
            )
            try:
                self.restore_game_state()
                logging.info(f"Game state restored")
            except Exception as e:
                logging.error(f"Failed to restore game state: {e}")
            return

        # Otherwise, select a new question
        self.daily_q = self._get_valid_question()

        if self.daily_q and self.daily_q.is_valid:
            # Always try to generate a hint using Gemini, falling back to provided hint if generation fails.
            original_hint = self.daily_q.hint
            logging.info(f"Generating hint for question {self.daily_q.id}...")
            try:
                new_hint = self.question_selector.get_hint_from_gemini(self.daily_q)
                if new_hint:
                    self.daily_q.hint = new_hint
                    logging.info(
                        f"Successfully generated hint for question {self.daily_q.id}."
                    )
                elif original_hint:
                    logging.warning(
                        f"Hint generation returned empty result for question {self.daily_q.id}. Using original hint."
                    )
                else:
                    logging.warning(
                        f"Hint generation returned empty result for question {self.daily_q.id} and no original hint available."
                    )
            except Exception as e:
                if original_hint:
                    logging.error(
                        f"Error generating hint for question {self.daily_q.id}: {e}. Using original hint."
                    )
                else:
                    logging.error(
                        f"Error generating hint for question {self.daily_q.id}: {e}. No original hint available."
                    )

            self.daily_question_id = self.data_manager.log_daily_question(self.daily_q)

            # Get the complete question data (handles both new and existing questions)
            daily_question_data = self.data_manager.get_todays_daily_question()
            if daily_question_data:
                self.daily_q, self.daily_question_id, self.question_db_id = (
                    daily_question_data
                )

            logging.info(f"Daily question set with ID: {self.daily_question_id}")

    def end_daily_game(self):
        """
        Ends the daily game by clearing the current question and resetting manager states.
        """
        logging.info("Ending daily game.")

        # Reset streaks for players who didn't answer correctly
        if self.daily_question_id:
            self.player_manager.reset_unanswered_streaks(self.daily_question_id)
            # Expire rest multipliers that weren't consumed today
            self.data_manager.clear_stale_rest_multipliers(self.daily_question_id)

        self.daily_q = None
        self.daily_question_id = None
        self.question_db_id = None

        for manager in self.managers.values():
            if hasattr(manager, "reset_daily_state"):
                manager.reset_daily_state()

    def add_subscriber(self, subscriber: Subscriber):
        self.data_manager.save_subscriber(subscriber)
        self.subscribed_contexts.add(subscriber)

    def remove_subscriber(self, subscriber: Subscriber):
        self.data_manager.delete_subscriber(subscriber)
        self.subscribed_contexts.discard(subscriber)

    def get_subscribed_users(self):
        return self.subscribed_contexts

    def _fetch_daily_events(self, daily_question_id: int) -> list:
        """
        Fetches and parses all game events (guesses and powerups) for a given daily question.
        """
        guesses = self.data_manager.get_guesses_for_daily_question(daily_question_id)
        powerups = self.data_manager.get_powerup_usages_for_question(daily_question_id)

        events = []
        for g in guesses:
            ts = g["guessed_at"]
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts)
                except ValueError:
                    pass
            events.append(GuessEvent(ts, g["player_id"], g["guess_text"]))

        for p in powerups:
            ts = p["used_at"]
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts)
                except ValueError:
                    pass

            target = p["target_user_id"]
            events.append(PowerUpEvent(ts, p["user_id"], p["powerup_type"], target))

        return events

    def restore_game_state(self):
        """
        Restores the game state from the database using DailyGameSimulator.
        """
        logging.info("Restoring game state from database...")
        if not self.daily_question_id:
            logging.warning("Cannot restore state without a daily question ID.")
            return

        # 1. Fetch all events for the day
        events = self._fetch_daily_events(self.daily_question_id)

        initial_players = self.data_manager.get_all_players()

        answers = [self.daily_q.answer] + self.data_manager.get_alternative_answers(
            self.question_db_id
        )
        hint_ts = self.data_manager.get_hint_sent_timestamp(self.daily_question_id)
        if isinstance(hint_ts, str):
            try:
                hint_ts = datetime.fromisoformat(hint_ts)
            except ValueError:
                logging.warning(f"Failed to parse hint timestamp: {hint_ts}")
                hint_ts = None

        simulator = DailyGameSimulator(
            self.daily_q,
            answers,
            hint_ts,
            events,
            initial_players,
            self.config,
        )

        # Run simulation (without end_of_day logic)
        simulator.run(apply_end_of_day=False)

        # Now restore state to PowerUpManager
        for player_id, state in simulator.daily_state.items():
            self.managers["powerup"].restore_daily_state(player_id, state)

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
        fastest_guessers: dict[int, str] = {}  # rank (1-based) -> player_id
        first_try_solver_ids = set()
        before_hint_solver_ids = set()
        players_answered_correctly_today = set()

        if show_daily_bonuses and self.daily_question_id:
            all_guesses = self.data_manager.read_guess_history()
            daily_correct_guesses = [
                g
                for g in all_guesses
                if g.get("daily_question_id") == self.daily_question_id
                and g.get("is_correct")
            ]
            players_answered_correctly_today = {
                g["player_id"] for g in daily_correct_guesses
            }
            # Sort by guessed_at to determine order
            daily_correct_guesses.sort(key=lambda x: x.get("guessed_at"))

            # Track all ranked fastest guessers (up to as many ranks as configured)
            fastest_csv_raw = self.config.get("JBOT_BONUS_FASTEST_CSV", "")
            num_fastest_ranks = (
                len([x for x in fastest_csv_raw.split(",") if x.strip()])
                if fastest_csv_raw
                else 1
            )
            for rank, guess in enumerate(
                daily_correct_guesses[:num_fastest_ranks], start=1
            ):
                fastest_guessers[rank] = guess["player_id"]

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

        emoji_fastest = self.config.get("JBOT_EMOJI_FASTEST")
        emoji_fastest_csv_raw = self.config.get("JBOT_EMOJI_FASTEST_CSV", "")
        emoji_fastest_list = (
            [e.strip() for e in emoji_fastest_csv_raw.split(",") if e.strip()]
            if emoji_fastest_csv_raw
            else []
        )
        emoji_first_try = self.config.get("JBOT_EMOJI_FIRST_TRY")
        emoji_before_hint = self.config.get("JBOT_EMOJI_BEFORE_HINT")
        emoji_streak = self.config.get("JBOT_EMOJI_STREAK")
        emoji_streak_frozen = self.config.get("JBOT_EMOJI_STREAK_FROZEN")

        # Powerup badges
        emoji_jinxed = self.config.get("JBOT_EMOJI_JINXED")
        emoji_silenced = self.config.get("JBOT_EMOJI_SILENCED")
        emoji_stolen_from = self.config.get("JBOT_EMOJI_STOLEN_FROM")
        emoji_stealing = self.config.get("JBOT_EMOJI_STEALING")
        emoji_rest = self.config.get("JBOT_EMOJI_REST")
        emoji_rest_wakeup = self.config.get("JBOT_EMOJI_REST_WAKEUP")

        powerup_badges = defaultdict(list)
        resting_player_ids = set()
        wakeup_player_ids = set()
        if self.daily_question_id:
            powerups = self.data_manager.get_powerup_usages_for_question(
                self.daily_question_id
            )
            for p in powerups:
                p_type = p["powerup_type"]
                user_id = p["user_id"]
                target_id = p["target_user_id"]

                if p_type == "rest":
                    resting_player_ids.add(user_id)
                elif p_type == "rest_wakeup":
                    wakeup_player_ids.add(user_id)

                if p_type == "jinx":
                    # Always show silenced emoji (attacker is silenced regardless)
                    powerup_badges[user_id].append(emoji_silenced)

                    # Only show jinxed emoji if target answered today
                    if target_id:
                        if (
                            show_daily_bonuses
                            and target_id in players_answered_correctly_today
                        ):
                            powerup_badges[target_id].append(emoji_jinxed)
                        elif not show_daily_bonuses:
                            powerup_badges[target_id].append(emoji_jinxed)
                elif p_type == "steal":
                    # Show stealing emoji if the target answered correctly today
                    # (i.e. the steal actually fired). The attacker doesn't need to
                    # have answered correctly - they steal when the target answers.
                    if (
                        show_daily_bonuses
                        and target_id in players_answered_correctly_today
                    ):
                        powerup_badges[user_id].append(emoji_stealing)
                    elif not show_daily_bonuses:
                        powerup_badges[user_id].append(emoji_stealing)

                    # Only show stolen_from emoji if target answered correctly today
                    if target_id:
                        if (
                            show_daily_bonuses
                            and target_id in players_answered_correctly_today
                        ):
                            powerup_badges[target_id].append(emoji_stolen_from)
                        elif not show_daily_bonuses:
                            powerup_badges[target_id].append(emoji_stolen_from)
                elif p_type == "rest":
                    powerup_badges[user_id].append(emoji_rest)

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
            # Only show streaks of 2+ when player answered today (or when not showing daily bonuses)
            if streak >= 2:
                if show_daily_bonuses:
                    if player_id in players_answered_correctly_today:
                        badges.append(f"{streak}{emoji_streak}")
                    elif player_id in resting_player_ids:
                        badges.append(f"{streak}{emoji_streak_frozen}")
                else:
                    badges.append(f"{streak}{emoji_streak}")

            if show_daily_bonuses:
                if player_id in first_try_solver_ids:
                    badges.append(emoji_first_try)
                if player_id in before_hint_solver_ids:
                    badges.append(emoji_before_hint)
                for rank, gid in fastest_guessers.items():
                    if player_id == gid:
                        if 0 < rank <= len(emoji_fastest_list):
                            badges.append(emoji_fastest_list[rank - 1])
                        else:
                            badges.append(emoji_fastest)
                        break
                if player_id in wakeup_player_ids:
                    badges.append(emoji_rest_wakeup)

                # Add powerup badges
                if player_id in powerup_badges:
                    badges.extend(powerup_badges[player_id])

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
        """Helper method to format a trivia question using standard format."""
        return self._format_full_message(
            "**--- Question! ---**",
            question,
            show_hint=False,
            show_answer=False,
        )

    def format_answer(self, question: Question) -> str:
        """Internal helper method to format a trivia answer."""
        min_display_size = 15
        pad_size = max(min_display_size - len(question.answer), 0) // 2
        padded_answer = question.answer.center(len(question.answer) + pad_size * 2, " ")
        base_msg = f"Answer: ||**{padded_answer}**||\n"

        if self.daily_question_id:
            alts = self.data_manager.get_alternative_answers(self.daily_question_id)
            if alts:
                alts_str = ", ".join(f"||**{a}**||" for a in alts)
                base_msg += f"(Also accepted: {alts_str})\n"

        return base_msg

    def _format_full_message(
        self,
        header: str,
        question: Question,
        show_hint: bool = False,
        show_answer: bool = False,
        extra_content: str = "",
    ) -> str:
        """
        Unified helper to format game messages consistently.
        """
        msg = f"{header}\n\n"

        # Standard Question Block
        msg += f"Category: **{question.category}**\n"
        msg += f"Value: **${question.clue_value}**\n"
        msg += f"Question: **{question.question}**\n"

        if show_hint and question.hint:
            msg += f"Hint: ||**{question.hint}**||\n"

        if show_answer:
            msg += self.format_answer(question)

        if extra_content:
            msg += f"\n{extra_content}"

        return msg

    def get_morning_message_content(self) -> str:
        """Generates the text for the morning question announcement."""
        if not self.daily_q:
            return "No question available for today."
        return self.format_question(self.daily_q)

    def get_reminder_message_content(self, tag_unanswered: bool) -> str:
        """Generates the reminder message, including tagging players who haven't answered."""
        if not self.daily_q:
            return "No question to remind about."

        try:
            # Get players who have guessed
            all_guesses = self.data_manager.read_guess_history()
            daily_guesses = [
                g
                for g in all_guesses
                if g.get("daily_question_id") == self.daily_question_id
            ]
            player_ids_who_guessed = {g.get("player_id") for g in daily_guesses}
            all_players = self.player_manager.get_all_players()
            player_ids_all = set(k for k in all_players.keys())
            player_ids_not_guessed = player_ids_all - player_ids_who_guessed

            mentions = ""
            if tag_unanswered and player_ids_not_guessed:
                mentions = " ".join(
                    [f"<@{player_id}>" for player_id in player_ids_not_guessed]
                )

            return self._format_full_message(
                "Friendly reminder to get your guesses in!",
                self.daily_q,
                show_hint=True,
                show_answer=False,
                extra_content=mentions,
            )

        except Exception as e:
            logging.error(f"Error generating reminder message content: {e}")
            return f"Friendly reminder to get your guesses in!\nQuestion: {self.daily_q.question}"

    def get_evening_message_content(self, guild=None) -> str:
        """Generates the evening message with answer and summary."""
        if not self.daily_q:
            return "No question to answer for today."

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

            player_display_list.sort(key=lambda x: x[0].lower())
            player_answers += "--Player answers--\n"
            for player_name, formatted_guesses_str in player_display_list:
                player_answers += f"**{player_name}**: {formatted_guesses_str}\n"

        return self._format_full_message(
            "Good evening players!\nHere is the answer to today's question:",
            self.daily_q,
            show_hint=True,
            show_answer=True,
            extra_content=player_answers,
        )

    def _mark_newly_correct_guesses(self, daily_question_id: str, new_answer: str):
        """
        Marks previously incorrect guesses as correct if they match the new answer.

        Args:
            daily_question_id: The ID of the daily question
            new_answer: The new alternative answer to check against
        """
        # Use DataManager to mark guesses as correct, using GuessHandler's matching logic
        num_updated = self.data_manager.mark_matching_guesses_as_correct(
            daily_question_id, new_answer, AnswerChecker().is_correct
        )

        if num_updated > 0:
            logging.info(
                f"Marked {num_updated} previously incorrect guesses as correct"
            )

    def recalculate_scores_for_new_answer(
        self, new_answer: str, admin_id: str, dry_run: bool = False
    ) -> dict:
        """
        Re-evaluates guesses for the current daily question against a new accepted answer.
        Returns a summary of changes.
        """
        # Use active question if available, otherwise fall back to most recent
        daily_q = self.daily_q
        daily_question_id = self.daily_question_id
        question_date = self.data_manager.get_today()

        if not daily_q or not daily_question_id:
            # Try to get the most recent daily question
            recent_question = self.data_manager.get_most_recent_daily_question()
            if not recent_question:
                return {"status": "error", "message": "No daily question found."}

            daily_q, daily_question_id, question_date = recent_question
            logging.info(
                f"Using most recent daily question from {question_date} (ID: {daily_question_id})"
            )

        # 1. Get Data
        hint_ts = self.data_manager.get_hint_sent_timestamp(daily_question_id)
        existing_alts = self.data_manager.get_alternative_answers(daily_question_id)
        old_answers = [daily_q.answer] + existing_alts
        new_answers = old_answers + [new_answer]

        events = self._fetch_daily_events(daily_question_id)

        # Try to get snapshot first
        snapshot = self.data_manager.get_daily_snapshot(daily_question_id)
        if snapshot:
            initial_states = snapshot
        else:
            players = self.player_manager.get_all_players()
            initial_states = players

        # 2. Run Scorer (Old)
        scorer_old = DailyGameSimulator(
            daily_q, old_answers, hint_ts, events, initial_states, self.config
        )
        results_old = scorer_old.run()

        # 3. Run Scorer (New)
        scorer_new = DailyGameSimulator(
            daily_q, new_answers, hint_ts, events, initial_states, self.config
        )
        results_new = scorer_new.run()

        # 4. Diff and Apply
        updated_players = 0
        total_refunded = 0
        details = []

        # Check if correcting an old question
        days_old = (self.data_manager.get_today() - question_date).days
        age_warning = ""
        if days_old > 0:
            age_warning = f" (Warning: This question is {days_old} day(s) old)"

        if not dry_run:
            self.data_manager.add_alternative_answer(
                daily_question_id, new_answer, admin_id
            )
            # Mark guesses as correct in the database if they match the new answer
            self._mark_newly_correct_guesses(daily_question_id, new_answer)

        for user_id, new_res in results_new.items():
            old_res = results_old.get(user_id, {"score_earned": 0, "streak_delta": 0})

            score_diff = new_res["score_earned"] - old_res["score_earned"]
            streak_diff = new_res["streak_delta"] - old_res["streak_delta"]

            if score_diff != 0 or streak_diff != 0:
                if not dry_run:
                    if score_diff != 0:
                        self.player_manager.update_score(user_id, score_diff)

                    if streak_diff != 0:
                        current_player = self.player_manager.get_player(user_id)
                        if current_player:
                            new_streak = current_player.answer_streak + streak_diff
                            self.player_manager.set_streak(user_id, max(0, new_streak))

                    self.data_manager.log_score_adjustment(
                        user_id,
                        admin_id,
                        score_diff,
                        f"Correction for answer: {new_answer}",
                    )

                total_refunded += score_diff
                updated_players += 1

                # Add to details
                player_name = (
                    initial_states[user_id].name
                    if user_id in initial_states
                    else user_id
                )
                old_bonus_keys = set(old_res.get("bonuses", {}).keys())
                new_bonus_keys = set(new_res.get("bonuses", {}).keys())
                newly_gained_keys = new_bonus_keys - old_bonus_keys
                details.append(
                    {
                        "name": player_name,
                        "score_before": new_res["initial_score"]
                        + old_res["score_earned"],
                        "score_after": new_res["final_score"],
                        "diff": score_diff,
                        "badges": scorer_new._get_badges(newly_gained_keys),
                    }
                )

        return {
            "status": "success",
            "updated_players": updated_players,
            "total_refunded": total_refunded,
            "details": details,
            "age_warning": age_warning,
        }
