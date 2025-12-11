import re
import logging
import jellyfish
from datetime import date, timedelta, datetime
from src.core.data_manager import DataManager
from data.readers.question import Question


from src.cfg.main import ConfigReader

config = ConfigReader()


class AlreadyAnsweredCorrectlyError(Exception):
    """Raised when a player tries to answer a question they have already answered correctly."""

    pass


class GuessHandler:
    """
    Handles guess processing and validation.
    """

    def __init__(
        self,
        data_manager: DataManager,
        player_manager,
        daily_question: Question,
        daily_question_id: int,
        managers: dict,
        fuzzy_threshold=2,
        reminder_time=None,
    ):
        self.data_manager = data_manager
        self.player_manager = player_manager
        self.daily_q = daily_question
        self.daily_question_id = daily_question_id
        self.managers = managers
        self.fuzzy_threshold = fuzzy_threshold
        self.reminder_time = reminder_time
        self.config = ConfigReader()

    def _normalize(self, text: str) -> str:
        """
        Applies a series of cleaning and normalization rules to a string.
        """
        if not text:
            return ""

        text = text.lower().strip()

        # Convert written numbers to digits
        replacements = {
            r"\bone\b": "1",
            r"\btwo\b": "2",
            r"\bthree\b": "3",
            r"\bfour\b": "4",
            r"\bfive\b": "5",
            r"\bsix\b": "6",
            r"\bseven\b": "7",
            r"\beight\b": "8",
            r"\bnine\b": "9",
            r"\bten\b": "10",
        }
        for word, num in replacements.items():
            text = re.sub(word, num, text)

        # Remove common stop words
        stop_words = [
            "a",
            "an",
            "the",
            "and",
            "or",
            "of",
            "to",
            "in",
            "on",
            "at",
            "by",
            "for",
            "with",
        ]
        pattern = r"\b(" + "|".join(stop_words) + r")\b"
        text = re.sub(pattern, "", text)

        # Remove all non-alphanumeric characters
        text = re.sub(r"[^\w\s]", "", text)

        # Replace multiple spaces with a single space
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def _is_correct_guess(self, guess: str, answer: str) -> bool:
        """
        Checks a guess against an answer using normalization, fuzzy matching, and token logic.
        """
        norm_g = self._normalize(guess)
        norm_a = self._normalize(answer)

        # Reject empty guesses
        if not norm_g:
            return False

        # Step A: Exact Match
        # Purpose: Handles exact matches and number conversions perfectly.
        if norm_g == norm_a:
            return True

        # Step B: Standard Fuzzy Match (Typos)
        # Calculate Levenshtein distance between normalized strings.
        # Allow a distance of <= 2.
        # Purpose: Handles simple typos like "clokc" vs "clock".
        # EXCEPTION: If the answer is numeric, skip fuzzy matching to prevent "150" matching "650".
        if not norm_a.isdigit():
            distance = jellyfish.levenshtein_distance(norm_g, norm_a)
            if distance <= 2:
                return True

        # Step C: Smart Token Match (Precision/Recall)
        tokens_g = set(norm_g.split())
        tokens_a = set(norm_a.split())

        # Avoid division by zero
        if not tokens_g or not tokens_a:
            return False

        intersection = tokens_g.intersection(tokens_a)
        recall = len(intersection) / len(tokens_a)
        precision = len(intersection) / len(tokens_g)

        # Subset Match (Venn Diagram): Precision == 1.0 AND Recall >= 0.5.
        # Example: Answer "Mountain Daylight Time", Guess "Mountain Time" -> PASS.
        if precision == 1.0 and recall >= 0.5:
            return True

        # Superset Match (Over-answering): Recall == 1.0 AND len(answer) > 3.
        # Example: Answer "Central", Guess "Central Standard Time" -> PASS.
        # Constraint: Ensure answer length > 3 to prevent Answer "War" matching Guess "Civil War".
        if recall == 1.0 and len(norm_a) > 3:
            return True

        return False

    def get_player_guesses(self, player_id: int) -> list:
        """
        Returns all guesses for the current daily question for the given player.
        """
        if not self.daily_question_id:
            return []
        guesses = self.data_manager.read_guess_history(user_id=player_id)
        # Only include guesses for the current daily question
        return [
            g.get("guess_text")
            for g in guesses
            if g.get("daily_question_id") == self.daily_question_id
        ]

    def has_answered_correctly_today(self, player_id: int) -> bool:
        """
        Checks if the player has already answered today's question correctly.
        """
        if not self.daily_question_id:
            return False

        guesses = self.data_manager.read_guess_history(user_id=player_id)
        for guess in guesses:
            if guess.get("daily_question_id") == self.daily_question_id and guess.get(
                "is_correct"
            ):
                return True
        return False

    def handle_guess(
        self, player_id: int, player_name: str, guess: str
    ) -> tuple[bool, int, int, list[str]]:
        """
        Handles the answer submitted by a player, logs it, and returns correctness.

        Args:
            player_id (int): The Discord ID of the player.
            player_name (str): The Discord display name of the player.
            guess (str): The player's guess.

        Returns:
            tuple: (is_correct, num_guesses, points_earned, bonus_messages)
        """
        if not self.daily_q:
            return False, 0, 0, []  # No active question

        # Check if the player has already answered correctly today
        if self.has_answered_correctly_today(player_id):
            raise AlreadyAnsweredCorrectlyError()

        g = guess.strip().lower()
        a = str(self.daily_q.answer).strip().lower()
        is_correct = self._is_correct_guess(g, a)

        points_earned = 0
        bonus_messages = []

        if is_correct:
            # Base Score
            points_earned = self.daily_q.clue_value or 100

            # Check First Solver (before logging this guess)
            existing_correct_count = self.data_manager.get_correct_guess_count(
                self.daily_question_id
            )
            if existing_correct_count == 0:
                bonus = int(self.config.get("JBOT_BONUS_FIRST_PLACE", 10))
                emoji = self.config.get("JBOT_EMOJI_FASTEST", "🥇")
                points_earned += bonus
                bonus_messages.append(f"{emoji} First to answer! (+{bonus})")

            # Check First Try (before logging this guess)
            previous_guesses = self.get_player_guesses(player_id)
            if len(previous_guesses) == 0:
                bonus = int(self.config.get("JBOT_BONUS_FIRST_TRY", 20))
                emoji = self.config.get("JBOT_EMOJI_FIRST_TRY", "🎯")
                points_earned += bonus
                bonus_messages.append(f"{emoji} First try! (+{bonus})")

            # Check Before Hint (before logging this guess)
            if self.reminder_time:
                now = datetime.now(self.reminder_time.tzinfo)
                if now.timetz() < self.reminder_time:
                    bonus = int(self.config.get("JBOT_BONUS_BEFORE_HINT", 10))
                    emoji = self.config.get("JBOT_EMOJI_BEFORE_HINT", "🧠")
                    points_earned += bonus
                    bonus_messages.append(f"{emoji} Before hint! (+{bonus})")

            # Check Streak
            # We need to get the player's current streak BEFORE incrementing it
            player = self.player_manager.get_player(str(player_id))
            current_streak = player.answer_streak if player else 0

            # Determine if streak continues
            last_correct_date = self.data_manager.get_last_correct_guess_date(
                str(player_id)
            )
            today = date.today()

            if last_correct_date == today:
                # Already answered correctly today (e.g. skipped question)
                new_streak = current_streak
            elif last_correct_date == today - timedelta(days=1):
                new_streak = current_streak + 1
            else:
                # Streak broken or new player
                new_streak = 1
                # Reset streak in DB so increment works correctly
                self.player_manager.reset_streak(str(player_id))

            if new_streak >= 2:
                streak_bonus_per_day = int(
                    self.config.get("JBOT_BONUS_STREAK_PER_DAY", 5)
                )
                streak_bonus_cap = int(self.config.get("JBOT_BONUS_STREAK_CAP", 25))
                emoji = self.config.get("JBOT_EMOJI_STREAK", "🔥")

                bonus = min(new_streak * streak_bonus_per_day, streak_bonus_cap)

                points_earned += bonus
                bonus_messages.append(f"{emoji} {new_streak} day streak! (+{bonus})")

            # Apply Score & Streak
            self.player_manager.get_or_create_player(str(player_id), player_name)
            self.player_manager.update_score(str(player_id), points_earned)
            if last_correct_date != today:
                self.player_manager.increment_streak(str(player_id), player_name)

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
                    logging.error(
                        f"Error calling on_guess for {type(manager).__name__}: {e}"
                    )
                    # Attempt to call with fewer arguments for backward compatibility
                    try:
                        manager.on_guess(player_id, is_correct)
                    except TypeError:
                        pass  # Or log that this also failed

        # Get the number of guesses for this question
        num_guesses = len(self.get_player_guesses(player_id))

        return is_correct, num_guesses, points_earned, bonus_messages
