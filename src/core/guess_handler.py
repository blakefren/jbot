import re
import logging
import jellyfish
from src.core.data_manager import DataManager
from data.readers.question import Question


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
        daily_question: Question,
        daily_question_id: int,
        managers: dict,
        fuzzy_threshold=2,
    ):
        self.data_manager = data_manager
        self.daily_q = daily_question
        self.daily_question_id = daily_question_id
        self.managers = managers
        self.fuzzy_threshold = fuzzy_threshold

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

        # Check for fuzzy match using Levenshtein distance
        distance = jellyfish.levenshtein_distance(norm_g, norm_a)
        if distance <= self.fuzzy_threshold:
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
    ) -> tuple[bool, int]:
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

        g = guess.strip().lower()
        a = str(self.daily_q.answer).strip().lower()
        is_correct = self._is_correct_guess(g, a)
        self.data_manager.log_player_guess(
            player_id, player_name, self.daily_question_id, g, is_correct
        )
        logging.info(f"Player {player_name} guessed '{g}'. Correct: {is_correct}")

        # Update player's answer streak
        player_manager = self.managers.get("player")
        if player_manager:
            player = player_manager.get_player(player_id)
            if player:
                if is_correct:
                    player.increment_streak()
                    player_manager.save_players()

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

        return is_correct, num_guesses
