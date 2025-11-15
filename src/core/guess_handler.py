import re
import logging
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
    ):
        self.data_manager = data_manager
        self.daily_q = daily_question
        self.daily_question_id = daily_question_id
        self.managers = managers

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
        num_guesses = len(self.get_player_guesses(player_id)) + 1

        return is_correct, num_guesses
