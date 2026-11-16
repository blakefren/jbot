from abc import ABC, abstractmethod
from contextlib import nullcontext
from functools import wraps
from src.core.events import GuessContext


def serialize_game_action(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        lock = getattr(self.data_manager, "game_action_lock", None)
        with lock if lock is not None else nullcontext():
            return method(self, *args, **kwargs)

    return wrapped


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
