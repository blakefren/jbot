from abc import ABC, abstractmethod


class BaseManager(ABC):
    """
    Abstract base class for game feature managers.
    """

    @abstractmethod
    def on_guess(self, player_id: int, player_name: str, guess: str, is_correct: bool):
        """
        Called when a player makes a guess.
        """
        pass
