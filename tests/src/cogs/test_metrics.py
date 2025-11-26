import unittest
from unittest.mock import AsyncMock, MagicMock

from src.cogs.metrics import Metrics


class TestMetricsCog(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.game = MagicMock()
        self.bot.send_message = AsyncMock()

        self.cog = Metrics(self.bot)

        self.ctx = MagicMock()
        self.ctx.author = MagicMock()
        self.ctx.author.id = 123
        self.ctx.author.display_name = "TestPlayer"
        self.ctx.guild = MagicMock()
        self.ctx.interaction = MagicMock()

    async def test_history_command(self):
        """Test the history command displays player history."""
        self.bot.game.get_player_history.return_value = "Player history text"

        await self.cog.history.callback(self.cog, self.ctx)

        self.bot.game.get_player_history.assert_called_once_with(123, "TestPlayer")
        self.bot.send_message.assert_called_once_with(
            "Player history text",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )

    async def test_leaderboard_command(self):
        """Test the leaderboard command displays the leaderboard."""
        self.bot.game.get_scores_leaderboard.return_value = "Leaderboard text"

        await self.cog.leaderboard.callback(self.cog, self.ctx)

        self.bot.game.get_scores_leaderboard.assert_called_once_with(self.ctx.guild)
        self.bot.send_message.assert_called_once_with(
            "Leaderboard text",
            interaction=self.ctx.interaction,
        )


class TestMetricsSetup(unittest.IsolatedAsyncioTestCase):
    async def test_setup(self):
        """Test that the setup function adds the cog."""
        from src.cogs.metrics import setup

        mock_bot = MagicMock()
        mock_bot.add_cog = AsyncMock()

        await setup(mock_bot)

        mock_bot.add_cog.assert_called_once()
        # Verify it's a Metrics instance
        call_args = mock_bot.add_cog.call_args
        self.assertIsInstance(call_args[0][0], Metrics)


if __name__ == "__main__":
    unittest.main()
