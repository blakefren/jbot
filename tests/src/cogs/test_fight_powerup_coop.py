import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.cogs.fight import Fight
from src.cogs.powerup import Powerup
from src.cogs.coop import Coop


class TestFightCog(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.game = MagicMock()
        self.bot.player_manager = MagicMock()
        self.bot.send_message = AsyncMock()
        self.cog = Fight(self.bot)

        self.ctx = MagicMock()
        self.ctx.author = MagicMock()
        self.ctx.author.id = "123"
        self.ctx.interaction = MagicMock()

    async def test_disrupt_not_powerup_mode(self):
        """Test disrupt command when not in POWERUP mode."""
        self.bot.game.mode.name = "NORMAL"

        await self.cog.disrupt.callback(self.cog, self.ctx, target_id="456")

        self.bot.send_message.assert_called_once_with(
            "This command is only available in POWERUP mode.",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )

    async def test_disrupt_in_powerup_mode(self):
        """Test disrupt command in POWERUP mode."""
        self.bot.game.mode.name = "POWERUP"
        self.bot.player_manager.get_all_players.return_value = {"123": MagicMock()}

        await self.cog.disrupt.callback(self.cog, self.ctx, target_id="456")

        self.bot.send_message.assert_called_once()

    async def test_shield_not_powerup_mode(self):
        """Test shield command when not in POWERUP mode."""
        self.bot.game.mode.name = "NORMAL"

        await self.cog.shield.callback(self.cog, self.ctx)

        self.bot.send_message.assert_called_once_with(
            "This command is only available in POWERUP mode.",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )

    async def test_shield_in_powerup_mode(self):
        """Test shield command in POWERUP mode."""
        self.bot.game.mode.name = "POWERUP"
        self.bot.player_manager.get_all_players.return_value = {"123": MagicMock()}

        await self.cog.shield.callback(self.cog, self.ctx)

        self.bot.send_message.assert_called_once()

    async def test_steal_not_powerup_mode(self):
        """Test steal command when not in POWERUP mode."""
        self.bot.game.mode.name = "NORMAL"

        await self.cog.steal.callback(self.cog, self.ctx, target_id="456")

        self.bot.send_message.assert_called_once_with(
            "This command is only available in POWERUP mode.",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )

    async def test_steal_in_powerup_mode(self):
        """Test steal command in POWERUP mode."""
        self.bot.game.mode.name = "POWERUP"
        self.bot.player_manager.get_all_players.return_value = {"123": MagicMock()}

        await self.cog.steal.callback(self.cog, self.ctx, target_id="456")

        self.bot.send_message.assert_called_once()


class TestFightSetup(unittest.IsolatedAsyncioTestCase):
    async def test_setup(self):
        """Test that the setup function adds the cog."""
        from src.cogs.fight import setup

        mock_bot = MagicMock()
        mock_bot.add_cog = AsyncMock()

        await setup(mock_bot)

        mock_bot.add_cog.assert_called_once()
        call_args = mock_bot.add_cog.call_args
        self.assertIsInstance(call_args[0][0], Fight)


class TestPowerupCog(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.game = MagicMock()
        self.bot.player_manager = MagicMock()
        self.bot.send_message = AsyncMock()
        self.cog = Powerup(self.bot)

        self.ctx = MagicMock()
        self.ctx.author = MagicMock()
        self.ctx.author.id = "123"
        self.ctx.interaction = MagicMock()

    async def test_wager_not_powerup_mode(self):
        """Test wager command when not in POWERUP mode."""
        self.bot.game.mode.name = "NORMAL"

        await self.cog.wager.callback(self.cog, self.ctx, amount=10)

        self.bot.send_message.assert_called_once_with(
            "This command is only available in POWERUP mode.",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )

    @patch("src.cogs.utils.PowerUpManager")
    async def test_wager_in_powerup_mode(self, mock_powerup_manager_class):
        """Test wager command in POWERUP mode."""
        self.bot.game.mode.name = "POWERUP"
        self.bot.player_manager.get_all_players.return_value = {"123": MagicMock()}

        mock_manager = MagicMock()
        mock_manager.wager_points.return_value = "Wagered 10 points!"
        mock_powerup_manager_class.return_value = mock_manager

        await self.cog.wager.callback(self.cog, self.ctx, amount=10)

        mock_manager.wager_points.assert_called_once_with("123", 10)
        self.bot.send_message.assert_called_once_with(
            "Wagered 10 points!", interaction=self.ctx.interaction
        )

    async def test_boss_fight_not_implemented(self):
        """Test boss_fight command returns not implemented message."""
        await self.cog.boss_fight.callback(self.cog, self.ctx)

        self.bot.send_message.assert_called_once_with(
            "This command is not yet implemented.",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )


class TestPowerupSetup(unittest.IsolatedAsyncioTestCase):
    async def test_setup(self):
        """Test that the setup function adds the cog."""
        from src.cogs.powerup import setup

        mock_bot = MagicMock()
        mock_bot.add_cog = AsyncMock()

        await setup(mock_bot)

        mock_bot.add_cog.assert_called_once()
        call_args = mock_bot.add_cog.call_args
        self.assertIsInstance(call_args[0][0], Powerup)


class TestCoopCog(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.game = MagicMock()
        self.bot.send_message = AsyncMock()
        self.cog = Coop(self.bot)

        self.ctx = MagicMock()
        self.ctx.author = MagicMock()
        self.ctx.author.id = "123"
        self.ctx.interaction = MagicMock()

    async def test_reinforce_not_coop_mode(self):
        """Test reinforce command when not in COOP mode."""
        self.bot.game.mode.name = "NORMAL"

        await self.cog.reinforce.callback(self.cog, self.ctx, target_id="456")

        self.bot.send_message.assert_called_once_with(
            "Reinforce is only available in COOP mode.",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )

    async def test_reinforce_in_coop_mode(self):
        """Test reinforce command in COOP mode (not yet implemented)."""
        self.bot.game.mode.name = "COOP"

        await self.cog.reinforce.callback(self.cog, self.ctx, target_id="456")

        self.bot.send_message.assert_called_once_with(
            "This command is not yet implemented.",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )

    async def test_reveal_not_implemented(self):
        """Test reveal command returns not implemented message."""
        await self.cog.reveal.callback(self.cog, self.ctx)

        self.bot.send_message.assert_called_once_with(
            "This command is not yet implemented.",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )

    async def test_teams_not_implemented(self):
        """Test teams command returns not implemented message."""
        await self.cog.teams.callback(self.cog, self.ctx)

        self.bot.send_message.assert_called_once_with(
            "This command is not yet implemented.",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )


class TestCoopSetup(unittest.IsolatedAsyncioTestCase):
    async def test_setup(self):
        """Test that the setup function adds the cog."""
        from src.cogs.coop import setup

        mock_bot = MagicMock()
        mock_bot.add_cog = AsyncMock()

        await setup(mock_bot)

        mock_bot.add_cog.assert_called_once()
        call_args = mock_bot.add_cog.call_args
        self.assertIsInstance(call_args[0][0], Coop)


if __name__ == "__main__":
    unittest.main()
