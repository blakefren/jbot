import re
import logging
import jellyfish
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
    ):
        self.data_manager = data_manager
        self.player_manager = player_manager
        self.daily_q = daily_question
        self.daily_question_id = daily_question_id
        self.managers = managers
        self.fuzzy_threshold = fuzzy_threshold
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

        # Remove articles (a, an, the)
        text = re.sub(r"\b(a|an|the)\b", "", text)

        # Remove all non-alphanumeric characters
        text = re.sub(r"[^\w\s]", "", text)

        # Replace multiple spaces with a single space
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def _is_correct_guess(self, guess: str, answer: str) -> bool:
        """
        Checks a guess against an answer using normalization and fuzzy matching.
        """
        norm_g = self._normalize(guess)
        norm_a = self._normalize(answer)

        # Reject short guesses unless the answer is also short
        if len(norm_g) <= 1 and len(norm_a) > 1:
            return False

        # Check for exact match
        if norm_g == norm_a:
            return True

        # If the answer is numeric, require exact match
        if norm_a.isdigit():
            return False

        # Dynamic distance limit based on answer length to avoid overly lenient
        # matching on short words while still permitting minor typos on longer ones.
        def _distance_limit(ans_len: int) -> int:
            # Revised thresholds: tighten for short (3-5) answers.
            if ans_len <= 2:
                return 0  # extremely short must be exact
            if ans_len <= 5:
                return 1  # short answers allow only a single edit
            if ans_len <= 8:
                return 2  # medium length permit minor typos
            if ans_len <= 12:
                return 3  # longer answers permit a bit more fuzziness
            return 4  # very long answers allow more typos

        distance = jellyfish.levenshtein_distance(norm_g, norm_a)
        limit = _distance_limit(len(norm_a))
        # Preserve ability to override via constructor by treating provided fuzzy_threshold
        # as a hard cap if smaller than the dynamic limit (tighter matching).
        if self.fuzzy_threshold is not None:
            limit = (
                min(limit, self.fuzzy_threshold) if self.fuzzy_threshold >= 0 else limit
            )

        if distance <= limit:
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
                points_earned += bonus
                bonus_messages.append(f"First to answer! (+{bonus})")

            # Check First Try (before logging this guess)
            previous_guesses = self.get_player_guesses(player_id)
            if len(previous_guesses) == 0:
                bonus = int(self.config.get("JBOT_BONUS_FIRST_TRY", 20))
                points_earned += bonus
                bonus_messages.append(f"First try! (+{bonus})")

            # Check Streak
            # We need to get the player's current streak BEFORE incrementing it
            player = self.player_manager.get_player(str(player_id))
            current_streak = player.answer_streak if player else 0

            # If they answer today, their streak becomes current_streak + 1
            new_streak = current_streak + 1

            if new_streak >= 2:
                streak_bonus_per_day = int(
                    self.config.get("JBOT_BONUS_STREAK_PER_DAY", 5)
                )
                streak_bonus_cap = int(self.config.get("JBOT_BONUS_STREAK_CAP", 25))

                bonus = min(new_streak * streak_bonus_per_day, streak_bonus_cap)

                points_earned += bonus
                bonus_messages.append(f"{new_streak} day streak! (+{bonus})")

            # Apply Score & Streak
            self.player_manager.get_or_create_player(str(player_id), player_name)
            self.player_manager.update_score(str(player_id), points_earned)
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
