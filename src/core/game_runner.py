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
from src.core.utils import parse_timestamp
from src.core.season_manager import SeasonManager


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
        self.guess_handler = None
        self.answer_checker = AnswerChecker()

        # Initialize PowerUpManager (always enabled)
        self.managers["powerup"] = PowerUpManager(
            self.player_manager, self.data_manager
        )
        logging.info("PowerUpManager enabled.")

        # Initialize SeasonManager (enabled via config flag)
        self.season_manager = SeasonManager(self.data_manager, self.config)
        if self.season_manager.is_enabled():
            logging.info("SeasonManager enabled.")
        else:
            logging.info("SeasonManager disabled (JBOT_ENABLE_SEASONS=False).")

        # Pending season announcements to be broadcast on next morning message
        self.pending_season_announcements: list[str] = []

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

    def _setup_new_question(self, force_new: bool = False) -> bool:
        """
        Selects a question, generates a hint, logs it, and wires up game state.
        Shared by set_daily_question (fresh day) and reset_daily_question (skip).

        When force_new=True (skip scenario) and a question is already active,
        rolls back all DB-persisted state (scores, streaks, season stats,
        pending_rest_multiplier) to the snapshot taken at the start of that
        question, then re-queues any hydrated overnight preloads so they
        transfer to the replacement question.

        Returns True on success, False if no valid question or logging fails.
        """
        # --- Rollback (skip path only) ---
        # Capture before anything overwrites self.daily_question_id.
        old_question_id = self.daily_question_id if force_new else None
        if old_question_id is not None:
            powerup_manager = self.managers.get("powerup")
            if powerup_manager:
                powerup_manager.rollback_to_snapshot(old_question_id)

        self.daily_q = self._get_valid_question()
        if not (self.daily_q and self.daily_q.is_valid):
            return False

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

        self.daily_question_id = self.data_manager.log_daily_question(
            self.daily_q, force_new=force_new
        )

        # Refresh from DB — recovers the canonical daily_question_id and
        # question_db_id, and handles race conditions where log returns None
        # but the record was already inserted.
        daily_question_data = self.data_manager.get_todays_daily_question()
        if daily_question_data:
            self.daily_q, self.daily_question_id, self.question_db_id = (
                daily_question_data
            )

        if self.daily_question_id is None:
            logging.error("Failed to log new daily question.")
            return False

        logging.info(f"Daily question set with ID: {self.daily_question_id}")

        # Clear any in-memory powerup state from the previous (or skipped) question,
        # then promote overnight pre-loads to the new question ID.
        for manager in self.managers.values():
            if hasattr(manager, "reset_daily_state"):
                manager.reset_daily_state()
        powerup_manager = self.managers.get("powerup")
        if powerup_manager:
            powerup_manager.hydrate_pending_powerups(self.daily_question_id)

        self._build_guess_handler()
        return True

    def reset_daily_question(self) -> bool:
        """
        Resets the daily question by selecting a new one.
        This is intended for admin use to skip a problematic or unwanted question.
        Prior guesses/powerup state for the skipped question are not carried over.
        """
        logging.info("Admin triggered reset of daily question.")
        result = self._setup_new_question(force_new=True)
        if result:
            logging.info(f"Daily question reset to new ID: {self.daily_question_id}")
        return result

    def set_daily_question(self):
        """
        Sets the daily question for today, generating a hint if needed.

        Note: Hint generation can block for 10+ seconds. Future improvement:
        make this async to prevent blocking Discord's event loop.
        """
        logging.debug(f"GameRunner.set_daily_question.")

        # Check for season transition (end old season, create new one if needed).
        # Must run before the question is set so scores are attributed to the
        # correct season from the start of the day.
        try:
            transitioned, season_msgs = self.season_manager.check_season_transition()
            self.pending_season_announcements.extend(season_msgs)

            # Check for season ending soon reminder (only when no transition today)
            if not transitioned:
                reminder = self.season_manager.get_reminder_announcement()
                if reminder:
                    self.pending_season_announcements.append(reminder)
        except Exception as e:
            logging.warning(f"Season transition check failed, skipping: {e}")

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
                powerup_manager = self.managers.get("powerup")
                if powerup_manager:
                    powerup_manager.hydrate_pending_powerups(self.daily_question_id)
                self.restore_game_state()
                logging.info(f"Game state restored")
            except Exception as e:
                logging.error(f"Failed to restore game state: {e}")
            self._build_guess_handler()
            return

        self._setup_new_question()

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
        self.guess_handler = None

        for manager in self.managers.values():
            if hasattr(manager, "reset_daily_state"):
                manager.reset_daily_state()

    def _build_guess_handler(self):
        """Constructs and caches the GuessHandler for the current question day."""
        self.guess_handler = GuessHandler(
            self.data_manager,
            self.player_manager,
            self.daily_q,
            self.daily_question_id,
            self.managers,
            reminder_time=self.reminder_time,
            config=self.config,
            answer_checker=self.answer_checker,
            season_manager=self.season_manager,
        )

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
            ts = parse_timestamp(g["guessed_at"])
            events.append(GuessEvent(ts, g["player_id"], g["guess_text"]))

        for p in powerups:
            ts = parse_timestamp(p["used_at"])
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
        hint_ts = parse_timestamp(
            self.data_manager.get_hint_sent_timestamp(self.daily_question_id)
        )

        simulator = DailyGameSimulator(
            self.daily_q,
            answers,
            hint_ts,
            events,
            initial_players,
            self.config,
            answer_checker=self.answer_checker,
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

        if not self.guess_handler:
            self._build_guess_handler()
        return self.guess_handler.handle_guess(player_id, player_name, guess)

    def _build_daily_badges(
        self, daily_question_id: int, show_daily_bonuses: bool
    ) -> dict[str, list[str]]:
        """
        Queries the DB and assembles per-player badge emoji lists for the leaderboard.
        Badge order per player: first_try → before_hint → fastest → rest_wakeup → powerup.
        Returns a dict mapping player_id to a list of emoji strings.
        """
        result: dict[str, list[str]] = defaultdict(list)

        players_answered_correctly_today: set = set()

        if show_daily_bonuses and daily_question_id:
            all_guesses = self.data_manager.read_guess_history()
            daily_correct_guesses = [
                g
                for g in all_guesses
                if g.get("daily_question_id") == daily_question_id
                and g.get("is_correct")
            ]
            players_answered_correctly_today = {
                g["player_id"] for g in daily_correct_guesses
            }
            daily_correct_guesses.sort(key=lambda x: x.get("guessed_at"))

            emoji_first_try = self.config.get("JBOT_EMOJI_FIRST_TRY")
            first_try_solvers = self.data_manager.get_first_try_solvers(
                daily_question_id
            )
            for p in first_try_solvers:
                result[p["id"]].append(emoji_first_try)

            hint_timestamp_str = self.data_manager.get_hint_sent_timestamp(
                daily_question_id
            )
            emoji_before_hint = self.config.get("JBOT_EMOJI_BEFORE_HINT")
            for g in daily_correct_guesses:
                if hint_timestamp_str:
                    if g.get("guessed_at") < hint_timestamp_str:
                        result[g["player_id"]].append(emoji_before_hint)
                else:
                    result[g["player_id"]].append(emoji_before_hint)

            emoji_fastest = self.config.get("JBOT_EMOJI_FASTEST")
            emoji_fastest_csv_raw = self.config.get("JBOT_EMOJI_FASTEST_CSV", "")
            emoji_fastest_list = (
                [e.strip() for e in emoji_fastest_csv_raw.split(",") if e.strip()]
                if emoji_fastest_csv_raw
                else []
            )
            fastest_csv_raw = self.config.get("JBOT_BONUS_FASTEST_CSV", "")
            num_fastest_ranks = (
                len([x for x in fastest_csv_raw.split(",") if x.strip()])
                if fastest_csv_raw
                else 1
            )
            for rank, guess in enumerate(
                daily_correct_guesses[:num_fastest_ranks], start=1
            ):
                badge = (
                    emoji_fastest_list[rank - 1]
                    if 0 < rank <= len(emoji_fastest_list)
                    else emoji_fastest
                )
                result[guess["player_id"]].append(badge)

            emoji_rest_wakeup = self.config.get("JBOT_EMOJI_REST_WAKEUP")
            if daily_question_id:
                powerups_for_wakeup = self.data_manager.get_powerup_usages_for_question(
                    daily_question_id
                )
                for p in powerups_for_wakeup:
                    if p["powerup_type"] == "rest_wakeup":
                        result[p["user_id"]].append(emoji_rest_wakeup)

        # Powerup badges (shown regardless of show_daily_bonuses, but only rendered
        # when show_daily_bonuses=True — see leaderboard caller)
        if daily_question_id:
            emoji_jinxed = self.config.get("JBOT_EMOJI_JINXED")
            emoji_silenced = self.config.get("JBOT_EMOJI_SILENCED")
            emoji_stolen_from = self.config.get("JBOT_EMOJI_STOLEN_FROM")
            emoji_stealing = self.config.get("JBOT_EMOJI_STEALING")
            emoji_rest = self.config.get("JBOT_EMOJI_REST")

            powerups = self.data_manager.get_powerup_usages_for_question(
                daily_question_id
            )
            for p in powerups:
                p_type = p["powerup_type"]
                user_id = p["user_id"]
                target_id = p["target_user_id"]

                if p_type in ("jinx", "jinx_late", "jinx_preload"):
                    result[user_id].append(emoji_silenced)
                    if target_id:
                        if show_daily_bonuses:
                            if target_id in players_answered_correctly_today:
                                result[target_id].append(emoji_jinxed)
                        else:
                            result[target_id].append(emoji_jinxed)
                elif p_type == "steal":
                    if show_daily_bonuses:
                        if target_id in players_answered_correctly_today:
                            result[user_id].append(emoji_stealing)
                            if target_id:
                                result[target_id].append(emoji_stolen_from)
                    else:
                        result[user_id].append(emoji_stealing)
                        if target_id:
                            result[target_id].append(emoji_stolen_from)
                elif p_type == "rest":
                    result[user_id].append(emoji_rest)

        return dict(result)

    def get_scores_leaderboard(self, guild=None, show_daily_bonuses=False) -> str:
        """Computes and formats the leaderboard string."""
        player_scores = self.data_manager.get_player_scores()

        if not player_scores:
            return "No scores available yet."

        all_streaks = {
            s["id"]: s["answer_streak"] for s in self.data_manager.get_player_streaks()
        }
        broken_streaks: dict[str, int] = {}
        # Zero out streaks for players who won't keep them today (evening leaderboard).
        # This mirrors the reset_unanswered_streaks logic so the display is accurate
        # even before end_daily_game() runs.
        if self.daily_question_id:
            keepers = self.data_manager.get_streak_keepers(self.daily_question_id)
            broken_streaks = {
                pid: s for pid, s in all_streaks.items() if pid not in keepers
            }
            streaks = {pid: s for pid, s in all_streaks.items() if pid in keepers}
        else:
            streaks = all_streaks

        badge_map = self._build_daily_badges(self.daily_question_id, show_daily_bonuses)

        emoji_streak = self.config.get("JBOT_EMOJI_STREAK")
        emoji_streak_broken = self.config.get("JBOT_EMOJI_STREAK_BROKEN", "💔")

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
            broken_streak = broken_streaks.get(player_id, 0)
            score = player["score"]

            badges = []
            if show_daily_bonuses:
                badges.extend(badge_map.get(player_id, []))

            badges_str = "".join(badges)

            all_player_data.append(
                {
                    "name": player_name,
                    "score": score,
                    "streak": streak,
                    "broken_streak": broken_streak,
                    "badges": badges_str,
                }
            )

        # Sort players by score (desc), then by name (asc)
        all_player_data.sort(key=lambda p: (-p["score"], p["name"]))

        # Determine column widths
        max_name = (
            max(len(p["name"]) for p in all_player_data) if all_player_data else 10
        )
        max_score = max(
            3,  # Num chars in "Pts" header
            (
                max(len(str(p["score"])) for p in all_player_data)
                if all_player_data
                else 0
            ),
        )
        max_streak = max(
            2,  # display width of streak emoji header
            max(
                (len(str(p["streak"])) for p in all_player_data if p["streak"] >= 1),
                default=0,
            ),
            (2 if any(p["broken_streak"] >= 1 for p in all_player_data) else 0),
        )
        max_badges = max(
            6,  # Num chars in "Badges" header
            (
                max(wcwidth.wcswidth(p["badges"]) for p in all_player_data)
                if all_player_data
                else 0
            ),
        )

        # Streak emoji header: emoji is 2 display-chars wide, so pad with spaces if column is wider
        streak_header = " " * max(0, max_streak - 2) + emoji_streak

        # Header
        header = f"🏆 {'Player':<{max_name}} {'Pts':<{max_score}} {streak_header}"
        if show_daily_bonuses:
            header += " Badges"
        header += "\n"

        divider = f"{'-'*2} {'-'*max_name} {'-'*max_score} {'-'*max_streak}"
        if show_daily_bonuses:
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
            streak_val = p_data["streak"]
            broken_streak_val = p_data["broken_streak"]
            badges = p_data["badges"]

            if streak_val >= 1:
                streak_str = f"{streak_val:>{max_streak}}"
            elif broken_streak_val >= 1:
                pad = max(0, max_streak - wcwidth.wcswidth(emoji_streak_broken))
                streak_str = " " * pad + emoji_streak_broken
            else:
                streak_str = f"{'':>{max_streak}}"

            # For ties, only show rank and score for the first player
            if p_data["score"] == last_score:
                body += f"{'':>2} {name:<{max_name}} {'':>{max_score}} {streak_str}"
            else:
                body += (
                    f"{rank:>2} {name:<{max_name}} {score:>{max_score}} {streak_str}"
                )

            if show_daily_bonuses:
                body += f" {badges}"

            body += "\n"

            last_score = p_data["score"]
        return f"```{header}{divider}{body}```"

    def format_season_leaderboard(self, season) -> str:
        """Format a season's leaderboard as a display string."""
        current_day, total_days = self.season_manager.get_season_progress(season)
        entries = self.season_manager.get_season_leaderboard(season.season_id)
        emoji_streak = self.config.get("JBOT_EMOJI_STREAK")
        header = f"**-- {season.season_name} (Day {current_day}/{total_days}) --**"
        if not entries:
            return f"{header}\nNo scores this season yet."
        lines = [header + "\n```"]
        for i, (score, player_name) in enumerate(entries, start=1):
            streak_str = (
                f" {emoji_streak}{score.current_streak}"
                if score.current_streak >= 1
                else ""
            )
            lines.append(f"{i:>2}. {player_name:<16} {score.points:>6} pts{streak_str}")
        lines.append("```")
        return "\n".join(lines)

    def get_active_leaderboard(self, guild=None, show_daily_bonuses=False) -> str:
        """Return the season leaderboard when seasons are active, otherwise all-time."""
        if self.season_manager.enabled:
            current_season = self.season_manager.get_or_create_current_season()
            if current_season:
                return self.format_season_leaderboard(current_season)
        return self.get_scores_leaderboard(guild, show_daily_bonuses=show_daily_bonuses)

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
        streak = player.answer_streak if player else 0
        pending_mult = player.pending_rest_multiplier if player else 0.0

        lines = [
            f"-- Your stats, {player_name} --",
            f"Score:         {score}",
            f"Streak:        {streak} day(s)",
            f"Correct:       {correct_guesses}/{total_guesses} ({correct_rate:.1f}%)",
        ]
        if pending_mult and pending_mult > 1.0:
            lines.append(f"Rest bonus:    ×{pending_mult} applies tomorrow")

        return "\n".join(lines)

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
            daily_question_id, new_answer, self.answer_checker.is_correct
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
            daily_q,
            old_answers,
            hint_ts,
            events,
            initial_states,
            self.config,
            answer_checker=self.answer_checker,
        )
        results_old = scorer_old.run()

        # 3. Run Scorer (New)
        scorer_new = DailyGameSimulator(
            daily_q,
            new_answers,
            hint_ts,
            events,
            initial_states,
            self.config,
            answer_checker=self.answer_checker,
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
                        "user_id": user_id,
                        "name": player_name,
                        "score_before": new_res["initial_score"]
                        + old_res["score_earned"],
                        "score_after": new_res["final_score"],
                        "diff": score_diff,
                        "badges": scorer_new._get_badges(newly_gained_keys),
                    }
                )

        # Detect resting players whose guess now matches the new answer.
        # Their pending rest multiplier should be cleared since they effectively answered.
        rest_cleared_players = []
        seen_resting: set[str] = set()
        for event in events:
            if not isinstance(event, GuessEvent):
                continue
            uid = event.user_id
            if uid in seen_resting:
                continue
            state = scorer_new.daily_state.get(uid)
            if (
                state
                and state.is_resting
                and self.answer_checker.is_correct(event.guess_text, new_answer)
            ):
                player_name = initial_states[uid].name if uid in initial_states else uid
                rest_cleared_players.append({"user_id": uid, "name": player_name})
                seen_resting.add(uid)
                if not dry_run:
                    self.data_manager.clear_pending_multiplier(uid)

        return {
            "status": "success",
            "updated_players": updated_players,
            "total_refunded": total_refunded,
            "details": details,
            "age_warning": age_warning,
            "rest_cleared_players": rest_cleared_players,
        }
