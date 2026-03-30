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

    async def test_jinx_enabled(self):
        # Mock the manager with target not yet answered (normal path → ephemeral)
        mock_manager = MagicMock()
        mock_manager.jinx.return_value = "Success"
        mock_manager.daily_state = {}  # target not in state → not answered
        self.bot.game.managers.get.return_value = mock_manager

        await self.cog.jinx.callback(self.cog, self.ctx, target=self.target_member)

        mock_manager.jinx.assert_called_once_with(
            "123", "456", self.bot.game.daily_question_id
        )
        self.bot.send_message.assert_awaited_once_with(
            "Success", interaction=self.ctx.interaction, ephemeral=True
        )

    async def test_jinx_target_already_answered_is_public(self):
        # When target has already answered, result should be public (ephemeral=False)
        mock_manager = MagicMock()
        mock_manager.jinx.return_value = "Late jinx!"
        target_state = MagicMock()
        target_state.is_correct = True
        mock_manager.daily_state = {"456": target_state}
        self.bot.game.managers.get.return_value = mock_manager

        await self.cog.jinx.callback(self.cog, self.ctx, target=self.target_member)

        self.bot.send_message.assert_awaited_once_with(
            "Late jinx!", interaction=self.ctx.interaction, ephemeral=False
        )

    async def test_rest_no_active_question(self):
        self.bot.game.daily_q = None
        await self.cog.rest.callback(self.cog, self.ctx)
        self.bot.send_message.assert_awaited_once_with(
            "There is no active question right now.",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )

    async def test_rest_enabled(self):
        self.bot.game.daily_q = MagicMock()
        self.bot.game.daily_q.answer = "Test Answer"
        mock_manager = MagicMock()
        mock_manager.rest.return_value = ("public msg", "private msg")
        self.bot.game.managers.get.return_value = mock_manager

        await self.cog.rest.callback(self.cog, self.ctx)

        mock_manager.rest.assert_called_once_with(
            "123", self.bot.game.daily_question_id, "Test Answer"
        )
        self.ctx.channel.send.assert_awaited_once_with("public msg")
        self.bot.send_message.assert_awaited_once_with(
            "private msg", interaction=self.ctx.interaction, ephemeral=True
        )

    async def test_steal_forward_is_ephemeral(self):
        # Target hasn't answered yet → forward steal stays ephemeral
        mock_manager = MagicMock()
        mock_manager.steal.return_value = "Stolen points"
        mock_manager.daily_state = {}  # target not in state → not answered
        self.bot.game.managers.get.return_value = mock_manager

        await self.cog.steal.callback(self.cog, self.ctx, target=self.target_member)

        mock_manager.steal.assert_called_once_with(
            "123", "456", self.bot.game.daily_question_id
        )
        self.bot.send_message.assert_awaited_once_with(
            "Stolen points", interaction=self.ctx.interaction, ephemeral=True
        )

    async def test_steal_target_already_answered_is_public(self):
        # Target already answered → retroactive steal resolves immediately, must be public
        mock_manager = MagicMock()
        mock_manager.steal.return_value = "Retro steal!"
        target_state = MagicMock()
        target_state.is_correct = True
        mock_manager.daily_state = {"456": target_state}
        self.bot.game.managers.get.return_value = mock_manager

        await self.cog.steal.callback(self.cog, self.ctx, target=self.target_member)

        mock_manager.steal.assert_called_once_with(
            "123", "456", self.bot.game.daily_question_id
        )
        self.bot.send_message.assert_awaited_once_with(
            "Retro steal!", interaction=self.ctx.interaction, ephemeral=False
        )

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
