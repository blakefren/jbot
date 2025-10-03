import pytest
from unittest.mock import MagicMock, AsyncMock
from bot.discord import DiscordBot
from bot.cogs.fight import Fight
from bot.cogs.powerup import Powerup
from bot.cogs.coop import Coop
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
        self.logger.get_guess_metrics.return_value = {
            "players": {
                "1": {
                    "score": 100,
                    "bet": 0,
                    "under_attack": False,
                    "active_shield": False,
                }
            }
        }
        self.question_selector.questions = []
        self.daily_q = MagicMock(spec=Question)
        self.daily_q.id = "q1"
        self.daily_q.answer = "answer"

    def handle_guess(self, player_id, player_name, guess):
        return guess == "answer"


def make_bot_and_cogs():
    game = DummyGame()
    config = MagicMock()
    config.get.return_value = "POWERUP"

    bot = MagicMock(spec=DiscordBot)
    bot.game = game
    bot.config = config
    bot.send_message = AsyncMock()

    fight_cog = Fight(bot)
    powerup_cog = Powerup(bot)
    coop_cog = Coop(bot)

    return bot, fight_cog, powerup_cog, coop_cog


import asyncio
import pytest


@pytest.mark.asyncio
async def test_disrupt_command():
    bot, fight_cog, _, _ = make_bot_and_cogs()
    ctx = DummyCtx()
    with pytest.MonkeyPatch.context() as m:

        class DummyManager:
            def __init__(self, players):
                pass

            def disrupt(self, aid, tid):
                return "disrupted!"

        m.setattr("modes.powerup.PowerUpManager", DummyManager)
        await fight_cog.disrupt.callback(fight_cog, ctx, "2")
        bot.send_message.assert_called_with("disrupted!", interaction=ctx.interaction)


@pytest.mark.asyncio
async def test_shield_command():
    bot, fight_cog, _, _ = make_bot_and_cogs()
    ctx = DummyCtx()
    with pytest.MonkeyPatch.context() as m:

        class DummyManager:
            def __init__(self, players):
                pass

            def use_shield(self, pid):
                return "shielded!"

        m.setattr("modes.powerup.PowerUpManager", DummyManager)
        await fight_cog.shield.callback(fight_cog, ctx)
        bot.send_message.assert_called_with("shielded!", interaction=ctx.interaction)


@pytest.mark.asyncio
async def test_wager_command():
    bot, _, powerup_cog, _ = make_bot_and_cogs()
    ctx = DummyCtx()
    with pytest.MonkeyPatch.context() as m:

        class DummyManager:
            def __init__(self, players):
                pass

            def wager_points(self, pid, amt):
                return "wagered!"

        m.setattr("modes.powerup.PowerUpManager", DummyManager)
        await powerup_cog.wager.callback(powerup_cog, ctx, 10)
        bot.send_message.assert_called_with("wagered!", interaction=ctx.interaction)


@pytest.mark.asyncio
async def test_reinforce_command():
    bot, _, _, coop_cog = make_bot_and_cogs()
    bot.game.mode.name = "COOP"  # Set mode to COOP for this test
    ctx = DummyCtx()
    with pytest.MonkeyPatch.context() as m:

        class DummyManager:
            def __init__(self, players):
                pass

            def reinforce(self, pid1, pid2):
                return "reinforced!"

        m.setattr("modes.powerup.PowerUpManager", DummyManager)
        await coop_cog.reinforce.callback(coop_cog, ctx, "2")
        bot.send_message.assert_called_with("reinforced!", interaction=ctx.interaction)


@pytest.mark.asyncio
async def test_steal_command():
    bot, fight_cog, _, _ = make_bot_and_cogs()
    ctx = DummyCtx()
    with pytest.MonkeyPatch.context() as m:

        class DummyManager:
            def __init__(self, players):
                pass

            def steal(self, thief, target):
                return "stolen!"

        m.setattr("modes.powerup.PowerUpManager", DummyManager)
        await fight_cog.steal.callback(fight_cog, ctx, "2")
        bot.send_message.assert_called_with("stolen!", interaction=ctx.interaction)
