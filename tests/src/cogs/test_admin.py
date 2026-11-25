import logging
import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from data.readers.question import Question
from src.cogs.admin import Admin
from tests.src.cogs._game_stack import build_game_stack


class TestAdminCog(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = build_game_stack(
            self,
            question=Question("Test question?", "Test answer", "Test", 100, "Old hint"),
        )
        self.game = self.stack.game
        self.data_manager = self.stack.data_manager
        self.player_manager = self.stack.player_manager

        # The Discord bot and its scheduler tasks are the external boundary.
        self.bot = MagicMock()
        self.bot.morning_message_task = AsyncMock()
        self.bot.reminder_message_task = AsyncMock()
        self.bot.evening_message_task = AsyncMock()
        self.bot.game = self.game
        self.bot.player_manager = self.player_manager
        self.bot.data_manager = self.data_manager

        self.cog = Admin(self.bot)

        self.ctx = MagicMock()
        self.ctx.defer = AsyncMock()
        self.ctx.send = AsyncMock()
        self.ctx.author = MagicMock()
        self.ctx.author.id = "admin_id_456"

    async def _resend(self, message_type, silent, regenerate_hint=False):
        await self.cog.resend.callback(
            self.cog,
            self.ctx,
            message_type=message_type,
            silent=silent,
            regenerate_hint=regenerate_hint,
        )

    def _stored_hint(self):
        return self.data_manager.get_todays_daily_question()[0].hint

    async def test_resend_morning_silent(self):
        """Tests resend command for morning message with silent=True."""
        await self._resend("morning", silent=True)

        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_called_once_with(silent=True)
        self.bot.reminder_message_task.assert_not_called()
        self.bot.evening_message_task.assert_not_called()
        self.ctx.send.assert_called_once_with(
            "Silently resent morning message.", ephemeral=True
        )

    async def test_resend_morning_not_silent(self):
        """Tests resend command for morning message with silent=False."""
        await self._resend("morning", silent=False)

        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_called_once_with(silent=False)
        self.bot.reminder_message_task.assert_not_called()
        self.bot.evening_message_task.assert_not_called()
        self.ctx.send.assert_called_once_with("Morning message resent.")

    async def test_resend_reminder_silent(self):
        """Tests resend command for reminder message with silent=True."""
        await self._resend("reminder", silent=True)

        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_not_called()
        self.bot.reminder_message_task.assert_called_once_with(silent=True)
        self.bot.evening_message_task.assert_not_called()
        self.ctx.send.assert_called_once_with(
            "Silently resent reminder message.", ephemeral=True
        )

    async def test_resend_reminder_not_silent(self):
        """Tests resend command for reminder message with silent=False."""
        await self._resend("reminder", silent=False)

        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_not_called()
        self.bot.reminder_message_task.assert_called_once_with(silent=False)
        self.bot.evening_message_task.assert_not_called()
        self.ctx.send.assert_called_once_with("Reminder message resent.")

    async def test_resend_evening_silent(self):
        """Tests resend command for evening message with silent=True."""
        await self._resend("evening", silent=True)

        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_not_called()
        self.bot.reminder_message_task.assert_not_called()
        self.bot.evening_message_task.assert_called_once_with(silent=True)
        self.ctx.send.assert_called_once_with(
            "Silently resent evening message.", ephemeral=True
        )

    async def test_resend_evening_not_silent(self):
        """Tests resend command for evening message with silent=False."""
        await self._resend("evening", silent=False)

        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_not_called()
        self.bot.reminder_message_task.assert_not_called()
        self.bot.evening_message_task.assert_called_once_with(silent=False)
        self.ctx.send.assert_called_once_with("Evening message resent.")

    async def test_resend_invalid_message_type(self):
        """Tests resend command with an invalid message type."""
        await self._resend("invalid", silent=False)

        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_not_called()
        self.bot.reminder_message_task.assert_not_called()
        self.bot.evening_message_task.assert_not_called()
        self.ctx.send.assert_called_once_with(
            "Invalid message type. Use 'morning', 'reminder', or 'evening'."
        )

    async def test_resend_with_regenerate_hint_success(self):
        """Tests resend command with regenerate_hint=True."""
        question = self.game.daily_q
        selector = self.stack.question_selector
        selector.get_hint_from_gemini.reset_mock()
        selector.get_hint_from_gemini.return_value = "New hint"

        await self._resend("reminder", silent=True, regenerate_hint=True)

        self.ctx.defer.assert_called_once()
        selector.get_hint_from_gemini.assert_called_once_with(question)
        self.assertEqual(self.game.daily_q.hint, "New hint")
        self.assertEqual(self._stored_hint(), "New hint")
        self.bot.reminder_message_task.assert_called_once_with(silent=True)

    async def test_resend_with_regenerate_hint_no_question(self):
        """Tests resend with regenerate_hint=True when there's no active question."""
        self.bot.game = build_game_stack(self, start_day=False).game

        await self._resend("reminder", silent=True, regenerate_hint=True)

        self.ctx.defer.assert_called_once()
        self.ctx.send.assert_called_once_with(
            "Cannot regenerate hint: no active question.", ephemeral=True
        )
        self.bot.reminder_message_task.assert_not_called()

    async def test_resend_with_regenerate_hint_generation_fails(self):
        """Tests resend when hint generation returns None."""
        self.stack.question_selector.get_hint_from_gemini.return_value = None

        await self._resend("reminder", silent=True, regenerate_hint=True)

        self.ctx.defer.assert_called_once()
        self.ctx.send.assert_called_once_with(
            "❌ Hint generation returned empty result.", ephemeral=True
        )
        self.assertEqual(self._stored_hint(), "Old hint")
        self.bot.reminder_message_task.assert_not_called()

    async def test_resend_with_regenerate_hint_exception(self):
        """Tests resend when hint generation raises an exception."""
        self.stack.question_selector.get_hint_from_gemini.side_effect = Exception(
            "API Error"
        )

        await self._resend("reminder", silent=True, regenerate_hint=True)

        self.ctx.defer.assert_called_once()
        call_args = self.ctx.send.call_args[0][0]
        self.assertIn("❌ Error generating hint:", call_args)
        self.assertIn("API Error", call_args)
        self.assertEqual(self._stored_hint(), "Old hint")
        self.bot.reminder_message_task.assert_not_called()

    async def test_refund_updates_player_data(self):
        """The refund command updates the stored score and audits the adjustment."""
        self.player_manager.get_or_create_player("player_id_123", "TestPlayer")
        self.player_manager.update_score("player_id_123", 100)
        member = MagicMock(spec=discord.Member)
        member.id = "player_id_123"
        member.display_name = "TestPlayer"
        member.mention = "@TestPlayer"

        await self.cog.refund.callback(
            self.cog, self.ctx, member, 50, reason="Test refund"
        )

        self.assertEqual(self.player_manager.get_player("player_id_123").score, 150)
        adjustments = self.stack.db.execute_query(
            "SELECT player_id, admin_id, amount, reason FROM score_adjustments"
        )
        self.assertEqual(
            [tuple(row.values()) for row in adjustments],
            [("player_id_123", "admin_id_456", 50, "Test refund")],
        )
        self.ctx.send.assert_called_once_with(
            "Refunded @TestPlayer: +50 (Score: 150). Reason: Test refund"
        )

    async def test_refund_creates_missing_player_and_sets_streak(self):
        member = MagicMock(spec=discord.Member)
        member.id = "new_player"
        member.display_name = "NewPlayer"
        member.mention = "@NewPlayer"

        await self.cog.refund.callback(
            self.cog, self.ctx, member, 25, 4, reason="Make good"
        )

        player = self.player_manager.get_player("new_player")
        self.assertEqual(
            (player.name, player.score, player.answer_streak), ("NewPlayer", 25, 4)
        )
        self.ctx.send.assert_called_once_with(
            "Refunded @NewPlayer: +25 (Score: 25, Streak: 4). Reason: Make good"
        )

    async def test_refund_player_not_found_after_refund(self):
        """Test refund command when player cannot be found after refund."""
        member = MagicMock(spec=discord.Member)
        member.id = "player_id_123"
        member.display_name = "TestPlayer"

        with patch.object(self.player_manager, "get_player", return_value=None):
            await self.cog.refund.callback(
                self.cog, self.ctx, member, 50, reason="Test refund"
            )

        self.ctx.send.assert_called_once_with(
            "Could not find player TestPlayer after refund."
        )
        self.assertEqual(
            self.stack.db.execute_query("SELECT * FROM score_adjustments"), []
        )

    def _subscribers(self):
        return {
            (sub.sub_id, sub.display_name, sub.is_channel)
            for sub in self.data_manager.get_all_subscribers()
        }

    async def test_subscribe_member(self):
        """Test subscribe command with a member."""
        member = MagicMock(spec=discord.Member)
        member.id = 123
        member.display_name = "TestMember"

        await self.cog.subscribe.callback(
            self.cog, self.ctx, subscribe=True, member=member, channel=None
        )

        self.ctx.defer.assert_called_once()
        self.assertEqual(self._subscribers(), {(123, "TestMember", False)})
        self.assertEqual(
            {sub.sub_id for sub in self.game.get_subscribed_users()}, {123}
        )
        self.ctx.send.assert_called_once_with(
            "Subscribed TestMember to daily questions."
        )

    async def test_unsubscribe_member(self):
        """Test unsubscribe command with a member."""
        member = MagicMock(spec=discord.Member)
        member.id = 123
        member.display_name = "TestMember"
        await self.cog.subscribe.callback(
            self.cog, self.ctx, subscribe=True, member=member, channel=None
        )
        self.ctx.send.reset_mock()

        await self.cog.subscribe.callback(
            self.cog, self.ctx, subscribe=False, member=member, channel=None
        )

        self.assertEqual(self._subscribers(), set())
        self.assertEqual(self.game.get_subscribed_users(), set())
        self.ctx.send.assert_called_once_with(
            "Unsubscribed TestMember from daily questions."
        )

    async def test_subscribe_channel(self):
        """Test subscribe command with a channel."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 456
        channel.name = "test-channel"

        await self.cog.subscribe.callback(
            self.cog, self.ctx, subscribe=True, member=None, channel=channel
        )

        self.ctx.defer.assert_called_once()
        self.assertEqual(self._subscribers(), {(456, "test-channel", True)})
        self.ctx.send.assert_called_once_with(
            "Subscribed test-channel to daily questions."
        )

    async def test_unsubscribe_channel(self):
        """Test unsubscribe command with a channel."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 456
        channel.name = "test-channel"
        await self.cog.subscribe.callback(
            self.cog, self.ctx, subscribe=True, member=None, channel=channel
        )
        self.ctx.send.reset_mock()

        await self.cog.subscribe.callback(
            self.cog, self.ctx, subscribe=False, member=None, channel=channel
        )

        self.assertEqual(self._subscribers(), set())
        self.ctx.send.assert_called_once_with(
            "Unsubscribed test-channel from daily questions."
        )

    async def test_subscribe_no_target(self):
        """Test subscribe command with no member or channel."""
        await self.cog.subscribe.callback(
            self.cog, self.ctx, subscribe=True, member=None, channel=None
        )

        self.ctx.defer.assert_called_once()
        self.ctx.send.assert_called_once_with(
            "Please provide a member or a channel to subscribe."
        )
        self.assertEqual(self._subscribers(), set())

    async def test_subscribe_both_targets(self):
        """Test subscribe command with both member and channel."""
        member = MagicMock(spec=discord.Member)
        channel = MagicMock(spec=discord.TextChannel)

        await self.cog.subscribe.callback(
            self.cog, self.ctx, subscribe=True, member=member, channel=channel
        )

        self.ctx.defer.assert_called_once()
        self.ctx.send.assert_called_once_with(
            "Please provide either a member or a channel, not both."
        )
        self.assertEqual(self._subscribers(), set())


class TestAdminSeasonCommand(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = build_game_stack(
            self,
            players=(("p1", "One"), ("p2", "Two"), ("p3", "Three")),
            seasons=True,
            start_day=False,
        )
        self.game = self.stack.game
        self.data_manager = self.stack.data_manager

        self.bot = MagicMock()
        self.bot.game = self.game
        self.bot.data_manager = self.data_manager
        self.cog = Admin(self.bot)

        self.ctx = MagicMock()
        self.ctx.defer = AsyncMock()
        self.ctx.send = AsyncMock()
        self.ctx.author = MagicMock()

        today = self.data_manager.get_today()
        self.season_id = self.data_manager.create_season(
            "April 2026",
            (today - timedelta(days=4)).isoformat(),
            (today + timedelta(days=25)).isoformat(),
        )
        for player_id in ("p1", "p2", "p3"):
            self.data_manager.initialize_player_season_score(player_id, self.season_id)

    def _season_is_active(self, season_id):
        return self.data_manager.get_season_by_id(season_id).is_active

    async def test_season_info_disabled(self):
        """Returns error when seasons are disabled."""
        self.game.season_manager.enabled = False
        await self.cog.season.callback(self.cog, self.ctx)
        self.ctx.send.assert_called_once_with(
            "Seasons are not enabled.", ephemeral=True
        )

    async def test_season_info_no_active_season(self):
        """Returns error when no active season exists."""
        self.data_manager.end_season(self.season_id)
        await self.cog.season.callback(self.cog, self.ctx)
        self.ctx.send.assert_called_once_with("No active season found.", ephemeral=True)

    async def test_season_info_with_challenge(self):
        """Default (no flags) returns season info card including challenge name."""
        self.data_manager.create_season_challenge(
            self.season_id, "Speed Demon", "Be fast", "⚡", {"type": "speed"}
        )

        await self.cog.season.callback(self.cog, self.ctx)

        self.ctx.send.assert_called_once()
        msg = self.ctx.send.call_args[0][0]
        self.assertIn("April 2026", msg)
        self.assertIn("Day 5/30", msg)
        self.assertIn("⚡ Speed Demon", msg)
        self.assertIn("Players:   3", msg)

    async def test_season_info_no_challenge(self):
        """Default (no flags) shows 'None' when no challenge is set."""
        await self.cog.season.callback(self.cog, self.ctx)

        msg = self.ctx.send.call_args[0][0]
        self.assertIn("Challenge: None", msg)

    async def test_season_end_no_active_question(self):
        """end:True finalizes the season and reports the next season name."""
        await self.cog.season.callback(self.cog, self.ctx, end=True)

        self.assertFalse(self._season_is_active(self.season_id))
        next_season = self.data_manager.get_current_season()
        self.assertNotEqual(next_season.season_id, self.season_id)
        msg = self.ctx.send.call_args[0][0]
        self.assertIn("April 2026", msg)
        self.assertIn(next_season.season_name, msg)

    async def test_season_end_blocked_mid_day(self):
        """end:True is blocked when a question is active and force is False."""
        self.game.set_daily_question()

        await self.cog.season.callback(self.cog, self.ctx, end=True, force=False)

        self.assertTrue(self._season_is_active(self.season_id))
        msg = self.ctx.send.call_args[0][0]
        self.assertIn("A question is active", msg)

    async def test_season_end_force_mid_day(self):
        """end:True force:True proceeds and logs a warning when question is active."""
        self.game.set_daily_question()

        with self.assertLogs(level=logging.WARNING) as logs:
            await self.cog.season.callback(self.cog, self.ctx, end=True, force=True)

        self.assertTrue(any("force-ending season" in line for line in logs.output))
        self.assertFalse(self._season_is_active(self.season_id))


class TestAdminSetup(unittest.IsolatedAsyncioTestCase):
    async def test_setup(self):
        """Test that the setup function adds the cog."""
        from src.cogs.admin import setup

        mock_bot = MagicMock()
        mock_bot.add_cog = AsyncMock()

        await setup(mock_bot)

        mock_bot.add_cog.assert_called_once()
        call_args = mock_bot.add_cog.call_args
        self.assertIsInstance(call_args[0][0], Admin)


if __name__ == "__main__":
    unittest.main()
