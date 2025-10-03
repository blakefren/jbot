import pytest
from unittest.mock import MagicMock
from bot.discord import DiscordBot, set_bot_commands
from modes.game_runner import GameRunner, GameType
from database.logger import Logger
from readers.question_selector import QuestionSelector
from readers.question import Question

class DummyCtx:
    def __init__(self, author_id="1", display_name="Player1"):
        self.author = MagicMock()
        self.author.id = author_id
        self.author.display_name = display_name
        self.guild = None
        self.channel = MagicMock()
        self.channel.id = 123
        self.interaction = MagicMock()

    async def send(self, content):
        self.last_message = content

class DummyGame(GameRunner):
    def __init__(self):
        selector = MagicMock(spec=QuestionSelector)
        logger = MagicMock(spec=Logger)
        super().__init__(selector, logger, mode=GameType.POWERUP)
        self.mode = GameType.POWERUP
        self.logger.get_guess_metrics.return_value = {"players": {"1": {"score": 100, "bet": 0, "under_attack": False, "active_shield": False}}}
        self.question_selector.questions = []
        self.daily_q = MagicMock(spec=Question)
        self.daily_q.id = "q1"
        self.daily_q.answer = "answer"
    def handle_guess(self, player_id, player_name, guess):
        return guess == "answer"

def make_bot():
    game = DummyGame()
    config = MagicMock()
    config.get.return_value = "POWERUP"
    bot = DiscordBot("token", game, config)
    set_bot_commands(bot)
    return bot

import asyncio
import pytest

@pytest.mark.asyncio
async def test_disrupt_command():
    bot = make_bot()
    ctx = DummyCtx()
    # Patch PowerUpManager
    with pytest.MonkeyPatch.context() as m:
        class DummyManager:
            def __init__(self, players): pass
            def disrupt(self, aid, tid): return "disrupted!"
        m.setattr("modes.powerup.PowerUpManager", DummyManager)
        await bot.tree.get_command("disrupt").callback(ctx, "2")
        # No exception = pass

@pytest.mark.asyncio
async def test_shield_command():
    bot = make_bot()
    ctx = DummyCtx()
    with pytest.MonkeyPatch.context() as m:
        class DummyManager:
            def __init__(self, players): pass
            def use_shield(self, pid): return "shielded!"
        m.setattr("modes.powerup.PowerUpManager", DummyManager)
        await bot.tree.get_command("shield").callback(ctx)

@pytest.mark.asyncio
async def test_wager_command():
    bot = make_bot()
    ctx = DummyCtx()
    with pytest.MonkeyPatch.context() as m:
        class DummyManager:
            def __init__(self, players): pass
            def wager_points(self, pid, amt): return "wagered!"
        m.setattr("modes.powerup.PowerUpManager", DummyManager)
        await bot.tree.get_command("wager").callback(ctx, 10)


@pytest.mark.asyncio
async def test_reinforce_command():
    bot = make_bot()
    ctx = DummyCtx()
    with pytest.MonkeyPatch.context() as m:
        class DummyManager:
            def __init__(self, players): pass
            def reinforce(self, pid1, pid2): return "reinforced!"
        m.setattr("modes.powerup.PowerUpManager", DummyManager)
        # Simulate command (if implemented)
        if bot.tree.get_command("reinforce"):
            await bot.tree.get_command("reinforce").callback(ctx, "2")

@pytest.mark.asyncio
async def test_steal_command():
    bot = make_bot()
    ctx = DummyCtx()
    with pytest.MonkeyPatch.context() as m:
        class DummyManager:
            def __init__(self, players): pass
            def steal(self, thief, target): return "stolen!"
        m.setattr("modes.powerup.PowerUpManager", DummyManager)
        # Simulate command (if implemented)
        if bot.tree.get_command("steal"):
            await bot.tree.get_command("steal").callback(ctx, "2")
