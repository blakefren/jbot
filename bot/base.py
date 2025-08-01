import abc

from log.logger import Logger
from modes.base import GameType

class MessagingBot(abc.ABC):
    """
    An abstract base class for a messaging bot.
    Defines the high-level behavior that any messaging bot should have.
    """
    def __init__(self, game: GameType, logger: Logger):
        self.game = game
        self.logger = logger

    @abc.abstractmethod
    async def run(self):
        """Starts the bot."""
        pass

    @abc.abstractmethod
    async def send_morning_message(self):
        """Sends the daily question to all subscribers."""
        pass
        
    @abc.abstractmethod
    async def send_evening_message(self):
        """Sends the daily answer to all subscribers."""
        pass

    @abc.abstractmethod
    async def send_message(self, recipient_id, content: str, is_channel: bool):
        """Sends a message to a specific user or channel."""
        pass

    @abc.abstractmethod
    async def process_incoming_message(self, message):
        """Processes an incoming message from a user."""
        pass
