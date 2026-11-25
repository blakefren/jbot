import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.cogs.power import Power
from src.core.events import PowerUpOutcome
from tests.src.cogs._game_stack import build_game_stack


class TestPowerCog(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = build_game_stack(
            self, players=(("123", "Attacker"), ("456", "Target"))
        )
        self.game = self.stack.game
        self.data_manager = self.stack.data_manager
        self.player_manager = self.stack.player_manager
        self.player_manager.set_streak("123", 8)
        self.powerups = self.game.managers["powerup"]

        self.bot = SimpleNamespace(game=self.game, send_message=AsyncMock())
        self.cog = Power(self.bot)
        self.ctx = AsyncMock()
        self.ctx.interaction = MagicMock()
        self.ctx.author.id = 123
        self.ctx.author.display_name = "Attacker"

        self.target_member = MagicMock()
        self.target_member.id = 456
        self.target_member.display_name = "Target"

    def _usages(self):
        return [
            (row["user_id"], row["powerup_type"], row["target_user_id"])
            for row in self.data_manager.get_powerup_usages_for_question(
                self.game.daily_question_id
            )
        ]

    def _target_answers(self):
        self.game.handle_guess(456, "Target", "4")

    def _sent(self):
        return self.bot.send_message.await_args

    async def test_jinx_forward_is_ephemeral(self):
        await self.cog.jinx.callback(self.cog, self.ctx, target=self.target_member)

        self.assertEqual(self._usages(), [("123", "jinx", "456")])
        self.assertEqual(self.powerups.daily_state["456"].jinxed_by, "123")
        self.bot.send_message.assert_awaited_once()
        args, kwargs = self._sent()
        self.assertIn("Jinx activated on Target", args[0])
        self.assertIs(kwargs["interaction"], self.ctx.interaction)
        self.assertIs(kwargs["ephemeral"], True)

    async def test_jinx_target_already_answered_is_public(self):
        self._target_answers()
        target_score = self.player_manager.get_player("456").score

        await self.cog.jinx.callback(self.cog, self.ctx, target=self.target_member)

        self.assertEqual(self._usages(), [("123", "jinx", "456")])
        self.assertGreater(self.player_manager.get_player("123").score, 0)
        self.assertLess(self.player_manager.get_player("456").score, target_score)
        self.bot.send_message.assert_awaited_once()
        args, kwargs = self._sent()
        self.assertIsInstance(args[0], PowerUpOutcome)
        self.assertIs(kwargs["ephemeral"], False)

    async def test_rest_no_active_question(self):
        stack = build_game_stack(self, players=(("123", "Attacker"),), start_day=False)
        bot = SimpleNamespace(game=stack.game, send_message=AsyncMock())
        cog = Power(bot)

        await cog.rest.callback(cog, self.ctx)

        bot.send_message.assert_awaited_once_with(
            "There is no active question right now.",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )
        self.assertEqual(stack.db.execute_query("SELECT * FROM powerup_usage"), [])

    async def test_rest_enabled(self):
        await self.cog.rest.callback(self.cog, self.ctx)

        self.assertEqual(self._usages(), [("123", "rest", None)])
        self.assertTrue(self.powerups.daily_state["123"].is_resting)
        self.assertGreater(self.data_manager.get_pending_multiplier("123"), 0)
        self.assertEqual(self.bot.send_message.await_count, 2)
        public_call, private_call = self.bot.send_message.await_args_list
        self.assertEqual(public_call.kwargs, {"interaction": self.ctx.interaction})
        self.assertEqual(
            private_call.kwargs,
            {"interaction": self.ctx.interaction, "ephemeral": True},
        )
        self.assertIn("4", private_call.args[0])

    async def test_steal_forward_is_ephemeral(self):
        await self.cog.steal.callback(self.cog, self.ctx, target=self.target_member)

        self.assertEqual(self._usages(), [("123", "steal", "456")])
        self.assertEqual(self.powerups.daily_state["456"].steal_attempt_by, "123")
        self.bot.send_message.assert_awaited_once()
        args, kwargs = self._sent()
        self.assertIs(kwargs["ephemeral"], True)

    async def test_steal_target_already_answered_is_public(self):
        self._target_answers()
        target_score = self.player_manager.get_player("456").score

        await self.cog.steal.callback(self.cog, self.ctx, target=self.target_member)

        self.assertEqual(self._usages(), [("123", "steal", "456")])
        self.assertGreater(self.player_manager.get_player("123").score, 0)
        self.assertLess(self.player_manager.get_player("456").score, target_score)
        self.assertLess(self.player_manager.get_player("123").answer_streak, 8)
        self.bot.send_message.assert_awaited_once()
        args, kwargs = self._sent()
        self.assertIsInstance(args[0], PowerUpOutcome)
        self.assertIs(kwargs["ephemeral"], False)

    async def test_jinx_error_is_ephemeral(self):
        """PowerUpError from jinx is sent back as an ephemeral reply."""
        await self.cog.jinx.callback(self.cog, self.ctx, target=self.target_member)
        self.bot.send_message.reset_mock()

        await self.cog.jinx.callback(self.cog, self.ctx, target=self.target_member)

        self.assertEqual(self._usages(), [("123", "jinx", "456")])
        self.bot.send_message.assert_awaited_once_with(
            "You have already used an attack power-up today.",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )

    async def test_steal_error_is_ephemeral(self):
        """PowerUpError from steal is sent back as an ephemeral reply."""
        await self.cog.steal.callback(self.cog, self.ctx, target=self.target_member)
        self.bot.send_message.reset_mock()

        await self.cog.steal.callback(self.cog, self.ctx, target=self.target_member)

        self.assertEqual(self._usages(), [("123", "steal", "456")])
        self.bot.send_message.assert_awaited_once_with(
            "You have already used an attack power-up today.",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )

    async def test_rest_error_is_ephemeral(self):
        """Exception from rest (e.g. PowerUpError) is sent back as an ephemeral reply."""
        await self.cog.rest.callback(self.cog, self.ctx)
        self.bot.send_message.reset_mock()

        await self.cog.rest.callback(self.cog, self.ctx)

        self.ctx.channel.send.assert_not_awaited()
        self.assertEqual(self._usages(), [("123", "rest", None)])
        self.bot.send_message.assert_awaited_once_with(
            "You are already resting today.",
            interaction=self.ctx.interaction,
            ephemeral=True,
        )

    async def test_rest_text_command_sends_dm(self):
        """When invoked as a text command (no interaction), private reveal goes to DM."""
        self.ctx.interaction = None

        await self.cog.rest.callback(self.cog, self.ctx)

        self.assertEqual(self._usages(), [("123", "rest", None)])
        self.ctx.channel.send.assert_awaited_once()
        self.ctx.author.send.assert_awaited_once()
        self.assertIn("4", self.ctx.author.send.await_args.args[0])
        self.bot.send_message.assert_not_awaited()

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


if __name__ == "__main__":
    unittest.main()
