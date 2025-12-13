import unittest
from unittest.mock import AsyncMock, MagicMock
from src.cogs.power import Power
from src.core.discord import DiscordBot


class TestPowerCog(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock(spec=DiscordBot)
        self.bot.game = MagicMock()
        self.bot.player_manager = MagicMock()
        self.bot.send_message = AsyncMock()

        self.cog = Power(self.bot)
        self.ctx = AsyncMock()
        self.ctx.interaction = MagicMock()
        self.ctx.author.id = 123
        self.ctx.author.display_name = "Attacker"

    async def test_disrupt_disabled(self):
        self.bot.game.features = {"fight": False}
        await self.cog.disrupt.callback(self.cog, self.ctx, target_id="456")
        self.bot.send_message.assert_awaited_once_with(
            "Fight track is not enabled.",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )

    async def test_disrupt_enabled(self):
        self.bot.game.features = {"fight": True}

        # Mock the manager
        mock_manager = MagicMock()
        mock_manager.disrupt.return_value = "Success"
        self.bot.game.managers.get.return_value = mock_manager

        await self.cog.disrupt.callback(self.cog, self.ctx, target_id="456")

        mock_manager.disrupt.assert_called_once_with("123", "456")
        self.bot.send_message.assert_awaited_once_with(
            "Success", interaction=self.ctx.interaction
        )

    async def test_shield_disabled(self):
        self.bot.game.features = {"fight": False}
        await self.cog.shield.callback(self.cog, self.ctx)
        self.bot.send_message.assert_awaited_once_with(
            "Fight track is not enabled.",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )

    async def test_wager_disabled(self):
        self.bot.game.features = {"powerup": False}
        await self.cog.wager.callback(self.cog, self.ctx, amount=10)
        self.bot.send_message.assert_awaited_once_with(
            "Power-up track is not enabled.",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )

    async def test_reinforce_disabled(self):
        self.bot.game.features = {"coop": False}
        await self.cog.reinforce.callback(self.cog, self.ctx, target_id="456")
        self.bot.send_message.assert_awaited_once_with(
            "Coop track is not enabled.",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )
