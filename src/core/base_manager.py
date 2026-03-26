from abc import ABC, abstractmethod
from src.core.events import GuessContext


class BaseManager(ABC):
    """
    Abstract base class for game feature managers.
    """

    @abstractmethod
    def on_guess(self, ctx: GuessContext) -> list[str]:
        """
        Called when a player makes a guess.
        Implementations may mutate ctx.points_earned to apply score adjustments.
        Returns a list of messages to append to the response.
        """
        pass
