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

        self.target_member = MagicMock()
        self.target_member.id = 456
        self.target_member.display_name = "Target"

    async def test_jinx_disabled(self):
        self.bot.game.features = {"fight": False}
        await self.cog.jinx.callback(self.cog, self.ctx, target=self.target_member)
        self.bot.send_message.assert_awaited_once_with(
            "Fight track is not enabled.",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )

    async def test_jinx_enabled(self):
        self.bot.game.features = {"fight": True}

        # Mock the manager
        mock_manager = MagicMock()
        mock_manager.jinx.return_value = "Success"
        self.bot.game.managers.get.return_value = mock_manager

        await self.cog.jinx.callback(self.cog, self.ctx, target=self.target_member)

        mock_manager.jinx.assert_called_once_with("123", "456")
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

    async def test_shield_enabled(self):
        self.bot.game.features = {"fight": True}
        mock_manager = MagicMock()
        mock_manager.use_shield.return_value = "Shield activated"
        self.bot.game.managers.get.return_value = mock_manager

        await self.cog.shield.callback(self.cog, self.ctx)

        mock_manager.use_shield.assert_called_once_with("123")
        self.bot.send_message.assert_awaited_once_with(
            "Shield activated", interaction=self.ctx.interaction, ephemeral=True
        )

    async def test_steal_disabled(self):
        self.bot.game.features = {"fight": False}
        await self.cog.steal.callback(self.cog, self.ctx, target=self.target_member)
        self.bot.send_message.assert_awaited_once_with(
            "Fight track is not enabled.",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )

    async def test_steal_enabled(self):
        self.bot.game.features = {"fight": True}
        mock_manager = MagicMock()
        mock_manager.steal.return_value = "Stolen points"
        self.bot.game.managers.get.return_value = mock_manager

        await self.cog.steal.callback(self.cog, self.ctx, target=self.target_member)

        mock_manager.steal.assert_called_once_with("123", "456")
        self.bot.send_message.assert_awaited_once_with(
            "Stolen points", interaction=self.ctx.interaction
        )

    # TODO: Re-enable these tests when the commands are re-enabled
    # async def test_wager_disabled(self):
    #     self.bot.game.features = {"powerup": False}
    #     await self.cog.wager.callback(self.cog, self.ctx, amount=10)
    #     self.bot.send_message.assert_awaited_once_with(
    #         "Power-up track is not enabled.",
    #         interaction=self.ctx.interaction,
    #         ephemeral=True,
    #     )

    # async def test_wager_enabled(self):
    #     self.bot.game.features = {"powerup": True}
    #     mock_manager = MagicMock()
    #     mock_manager.place_wager.return_value = "Wager placed"
    #     self.bot.game.managers.get.return_value = mock_manager

    #     await self.cog.wager.callback(self.cog, self.ctx, amount=10)

    #     mock_manager.place_wager.assert_called_once_with("123", 10)
    #     self.bot.send_message.assert_awaited_once_with(
    #         "Wager placed", interaction=self.ctx.interaction
    #     )

    # async def test_teamup_disabled(self):
    #     self.bot.game.features = {"coop": False}
    #     await self.cog.teamup.callback(self.cog, self.ctx, target_id="456")
    #     self.bot.send_message.assert_awaited_once_with(
    #         "Coop track is not enabled.",
    #         interaction=self.ctx.interaction,
    #         ephemeral=True,
    #     )

    # async def test_teamup_enabled(self):
    #     self.bot.game.features = {"coop": True}
    #     mock_manager = MagicMock()
    #     mock_manager.teamup.return_value = "Reinforced"
    #     self.bot.game.managers.get.return_value = mock_manager

    #     await self.cog.teamup.callback(self.cog, self.ctx, target_id="456")

    #     mock_manager.teamup.assert_called_once_with("123", "456")
    #     self.bot.send_message.assert_awaited_once_with(
    #         "Reinforced", interaction=self.ctx.interaction
    #     )

    # async def test_reveal_disabled(self):
    #     self.bot.game.features = {"coop": False}
    #     await self.cog.reveal.callback(self.cog, self.ctx)
    #     self.bot.send_message.assert_awaited_once_with(
    #         "Coop track is not enabled.",
    #         interaction=self.ctx.interaction,
    #         ephemeral=True,
    #     )

    # async def test_reveal_enabled(self):
    #     self.bot.game.features = {"coop": True}
    #     await self.cog.reveal.callback(self.cog, self.ctx)
    #     self.bot.send_message.assert_awaited_once_with(
    #         "This command is not yet implemented.",
    #         interaction=self.ctx.interaction,
    #         ephemeral=True,
    #     )

    async def test_power_group(self):
        """Test the power group command sends help."""
        self.ctx.invoked_subcommand = None
        await self.cog.power.callback(self.cog, self.ctx)
        self.ctx.send_help.assert_awaited_once_with(self.ctx.command)

    async def test_setup(self):
        """Test the setup function."""
        from src.cogs.power import setup

        mock_bot = MagicMock()
        mock_bot.add_cog = AsyncMock()
        await setup(mock_bot)
        mock_bot.add_cog.assert_called_once()
