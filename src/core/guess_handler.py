import re
import logging
import jellyfish
from datetime import date, timedelta, datetime
from src.core.data_manager import DataManager
from data.readers.question import Question
from src.core.scoring import ScoreCalculator


from src.cfg.main import ConfigReader

CRUCIAL_MODIFIERS = {"north", "south", "east", "west", "new", "no"}


class AlreadyAnsweredCorrectlyError(Exception):
    """Raised when a player tries to answer a question they have already answered correctly."""

    pass


class JinxedError(Exception):
    """Raised when a player is jinxed and cannot answer."""

    def __init__(self, message):
        self.message = message
        super().__init__(message)


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
        self.score_calculator = ScoreCalculator(self.config)

        if self.data_manager:
            self.alternative_answers = self.data_manager.get_alternative_answers(
                self.daily_question_id
            )
        else:
            self.alternative_answers = []

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

    def _get_adaptive_limit(self, text: str) -> int:
        """
        Returns the allowed edit distance based on string length.
        """
        length = len(text)
        if length < 3:
            return 0  # Exact match only
        elif length <= 5:
            return 1  # Strict for short words
        else:
            return 2  # Standard tolerance

    def _is_token_match(self, token1: str, token2: str) -> bool:
        """
        Returns True if tokens match by Edit Distance (Typos) OR Jaro-Winkler (Root/Suffix).
        """
        # 1. Check Edit Distance (Adaptive Limit)
        limit = self._get_adaptive_limit(token2)
        dist = jellyfish.damerau_levenshtein_distance(token1, token2)

        if dist <= limit:
            return True

        # 2. Check Jaro-Winkler (Stemming/Suffix check)
        # 0.90 is a safe, high threshold that requires a strong prefix match.
        score = jellyfish.jaro_winkler_similarity(token1, token2)
        if score >= 0.90:
            return True

        return False

    def _smart_token_match(self, guess: str, answer: str) -> bool:
        """
        Checks if tokens match using Damerau-Levenshtein and adaptive thresholds.
        """
        tokens_g = guess.split()
        tokens_a = answer.split()

        if not tokens_g or not tokens_a:
            return False

        # Recall: Percentage of Answer words found in Guess
        matches_a = 0
        matched_answer_tokens = set()
        for ta in tokens_a:
            # Find closest token in guess
            if any(self._is_token_match(tg, ta) for tg in tokens_g):
                matches_a += 1
                matched_answer_tokens.add(ta)

        # --- NEW: CRUCIAL MODIFIER GUARD ---
        # Find which words in the answer were NOT found in the guess
        missing_tokens = set(tokens_a) - matched_answer_tokens

        # Check if we dropped something important
        if not missing_tokens.isdisjoint(CRUCIAL_MODIFIERS):
            return False

        recall = matches_a / len(tokens_a)

        # Precision: Percentage of Guess words found in Answer
        matches_g = 0
        for tg in tokens_g:
            matched = False
            for ta in tokens_a:
                if self._is_token_match(tg, ta):
                    matched = True
                    break
            if matched:
                matches_g += 1

        precision = matches_g / len(tokens_g)

        # Subset Match (Venn Diagram): Precision == 1.0 AND Recall >= 0.5.
        if precision == 1.0 and recall >= 0.5:
            return True

        # Superset Match (Over-answering): Recall == 1.0 AND len(answer) > 3.
        if recall == 1.0 and len(answer) > 3:
            return True

        return False

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
        if norm_g == norm_a:
            return True

        # Numeric Exception
        if norm_a.isdigit():
            return norm_g == norm_a

        # Step B: The Single-Word Branch
        answer_words = norm_a.split()
        if len(answer_words) == 1:
            if self._is_token_match(norm_g, norm_a):
                return True

        # Step C: Smart Token Match
        result = self._smart_token_match(norm_g, norm_a)
        return result

    @staticmethod
    def check_answer_match(guess: str, answer: str) -> bool:
        """
        Static method to check if a guess matches an answer.
        Creates a temporary GuessHandler instance to use the full matching logic.

        Args:
            guess: The player's guess (will be normalized)
            answer: The correct answer (will be normalized)

        Returns:
            bool: True if the guess matches the answer
        """
        # Create a minimal GuessHandler instance just for matching
        handler = GuessHandler(
            data_manager=None,
            player_manager=None,
            daily_question=Question(
                question="temp", answer=answer, category="temp", clue_value=0
            ),
            daily_question_id=0,
            managers={},
        )
        return handler._is_correct_guess(guess, answer)

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

        # Check if hint has been sent
        hint_timestamp = self.data_manager.get_hint_sent_timestamp(
            self.daily_question_id
        )
        hint_sent = hint_timestamp is not None

        # Check if player is allowed to answer (e.g. Jinxed)
        for manager in self.managers.values():
            if hasattr(manager, "can_answer"):
                try:
                    can_answer, reason = manager.can_answer(
                        str(player_id), hint_sent=hint_sent
                    )
                except TypeError:
                    # Fallback for managers that don't accept hint_sent
                    can_answer, reason = manager.can_answer(str(player_id))

                if not can_answer:
                    raise JinxedError(reason)

        g = guess.strip().lower()
        a = str(self.daily_q.answer).strip().lower()
        is_correct = self._is_correct_guess(g, a)

        # Check alternative answers if primary answer is incorrect
        if not is_correct:
            for alt_answer in self.alternative_answers:
                alt_a = str(alt_answer).strip().lower()
                if self._is_correct_guess(g, alt_a):
                    is_correct = True
                    break

        points_earned = 0
        bonus_messages = []
        bonus_values = {}

        if is_correct:
            # Gather inputs for ScoreCalculator
            base_value = self.daily_q.clue_value or 100

            # Check Rank (before logging this guess)
            existing_correct_count = self.data_manager.get_correct_guess_count(
                self.daily_question_id
            )
            answer_rank = existing_correct_count + 1

            # Check Attempt Number (before logging this guess)
            previous_guesses = self.get_player_guesses(player_id)
            guesses_count = len(previous_guesses) + 1

            # Check Before Hint (before logging this guess)
            is_before_hint = False
            if self.reminder_time:
                now = datetime.now(self.reminder_time.tzinfo)
                if now.timetz() < self.reminder_time:
                    is_before_hint = True

            # Determine Streak details
            player = self.player_manager.get_player(str(player_id))
            current_streak = player.answer_streak if player else 0

            last_correct_date = self.data_manager.get_last_correct_guess_date(
                str(player_id)
            )
            today = self.data_manager.get_today()

            if last_correct_date == today:
                # Already answered correctly today (e.g. skipped question)
                new_streak = current_streak
            else:
                new_streak = current_streak + 1

            # Calculate Points via shared engine
            points_earned, bonus_values, bonus_messages = (
                self.score_calculator.calculate_points(
                    question_value=base_value,
                    guesses_count=guesses_count,
                    is_before_hint=is_before_hint,
                    answer_rank=answer_rank,
                    streak_length=new_streak,
                )
            )

            # Apply Score & Streak
            self.player_manager.get_or_create_player(str(player_id), player_name)
            self.player_manager.update_score(str(player_id), points_earned)
            if last_correct_date != today:
                self.player_manager.increment_streak(str(player_id), player_name)

        self.data_manager.log_player_guess(
            player_id, player_name, self.daily_question_id, g, is_correct
        )
        logging.info(f"Player {player_name} guessed '{g}'. Correct: {is_correct}")

        # Track points earned for message display
        points_tracker = {"earned": points_earned}

        # Resolve with active managers
        for manager in self.managers.values():
            if manager is not None and not isinstance(manager, type):
                try:
                    # Try calling with newest signature (including points_tracker)
                    msgs = manager.on_guess(
                        player_id,
                        player_name,
                        guess,
                        is_correct,
                        points_earned,
                        bonus_values,
                        bonus_messages,
                        points_tracker,
                        question_id=self.daily_question_id,
                    )
                    if msgs and isinstance(msgs, list):
                        bonus_messages.extend(msgs)
                except TypeError:
                    # Fallback to previous signature (without points_tracker)
                    try:
                        msgs = manager.on_guess(
                            player_id,
                            player_name,
                            guess,
                            is_correct,
                            points_earned,
                            bonus_values,
                            bonus_messages,
                        )
                        if msgs and isinstance(msgs, list):
                            bonus_messages.extend(msgs)
                    except TypeError:
                        # Fallback to old signature (without bonus_messages)
                        try:
                            msgs = manager.on_guess(
                                player_id,
                                player_name,
                                guess,
                                is_correct,
                                points_earned,
                                bonus_values,
                            )
                            if msgs and isinstance(msgs, list):
                                bonus_messages.extend(msgs)
                        except TypeError as e:
                            logging.error(
                                f"Error calling on_guess for {type(manager).__name__}: {e}"
                            )
                            # Attempt to call with fewer arguments for backward compatibility
                            try:
                                manager.on_guess(player_id, is_correct)
                            except TypeError:
                                pass  # Or log that this also failed

        # Update points_earned from tracker
        points_earned = points_tracker["earned"]

        # Get the number of guesses for this question
        num_guesses = len(self.get_player_guesses(player_id))

        return is_correct, num_guesses, points_earned, bonus_messages
