import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from src.cogs.admin import Admin
from src.core.player_manager import PlayerManager
from src.core.game_runner import GameRunner
from src.core.subscriber import Subscriber
from db.database import Database


class TestAdminCog(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.morning_message_task = AsyncMock()
        self.bot.reminder_message_task = AsyncMock()
        self.bot.evening_message_task = AsyncMock()
        self.bot.tree = MagicMock()
        self.bot.tree.sync = AsyncMock()

        # Mocks for refund test
        self.bot.game = MagicMock(spec=GameRunner)
        self.bot.player_manager = MagicMock(spec=PlayerManager)
        self.bot.data_manager = MagicMock()
        self.bot.data_manager.db = MagicMock(spec=Database)

        self.cog = Admin(self.bot)

        self.ctx = MagicMock()
        self.ctx.defer = AsyncMock()
        self.ctx.send = AsyncMock()
        self.ctx.author = MagicMock()
        self.ctx.author.id = "admin_id_456"

    async def test_resend_morning_silent(self):
        """Tests resend command for morning message with silent=True."""
        await self.cog.resend.callback(
            self.cog,
            self.ctx,
            message_type="morning",
            silent=True,
            regenerate_hint=False,
        )

        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_called_once_with(silent=True)
        self.bot.reminder_message_task.assert_not_called()
        self.bot.evening_message_task.assert_not_called()
        self.ctx.send.assert_called_once_with(
            "Silently resent morning message.", ephemeral=True
        )

    async def test_resend_morning_not_silent(self):
        """Tests resend command for morning message with silent=False."""
        await self.cog.resend.callback(
            self.cog,
            self.ctx,
            message_type="morning",
            silent=False,
            regenerate_hint=False,
        )

        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_called_once_with(silent=False)
        self.bot.reminder_message_task.assert_not_called()
        self.bot.evening_message_task.assert_not_called()
        self.ctx.send.assert_called_once_with("Morning message resent.")

    async def test_resend_reminder_silent(self):
        """Tests resend command for reminder message with silent=True."""
        await self.cog.resend.callback(
            self.cog,
            self.ctx,
            message_type="reminder",
            silent=True,
            regenerate_hint=False,
        )

        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_not_called()
        self.bot.reminder_message_task.assert_called_once_with(silent=True)
        self.bot.evening_message_task.assert_not_called()
        self.ctx.send.assert_called_once_with(
            "Silently resent reminder message.", ephemeral=True
        )

    async def test_resend_reminder_not_silent(self):
        """Tests resend command for reminder message with silent=False."""
        await self.cog.resend.callback(
            self.cog,
            self.ctx,
            message_type="reminder",
            silent=False,
            regenerate_hint=False,
        )

        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_not_called()
        self.bot.reminder_message_task.assert_called_once_with(silent=False)
        self.bot.evening_message_task.assert_not_called()
        self.ctx.send.assert_called_once_with("Reminder message resent.")

    async def test_resend_evening_silent(self):
        """Tests resend command for evening message with silent=True."""
        await self.cog.resend.callback(
            self.cog,
            self.ctx,
            message_type="evening",
            silent=True,
            regenerate_hint=False,
        )

        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_not_called()
        self.bot.reminder_message_task.assert_not_called()
        self.bot.evening_message_task.assert_called_once_with(silent=True)
        self.ctx.send.assert_called_once_with(
            "Silently resent evening message.", ephemeral=True
        )

    async def test_resend_evening_not_silent(self):
        """Tests resend command for evening message with silent=False."""
        await self.cog.resend.callback(
            self.cog,
            self.ctx,
            message_type="evening",
            silent=False,
            regenerate_hint=False,
        )

        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_not_called()
        self.bot.reminder_message_task.assert_not_called()
        self.bot.evening_message_task.assert_called_once_with(silent=False)
        self.ctx.send.assert_called_once_with("Evening message resent.")

    async def test_resend_invalid_message_type(self):
        """Tests resend command with an invalid message type."""
        await self.cog.resend.callback(
            self.cog,
            self.ctx,
            message_type="invalid",
            silent=False,
            regenerate_hint=False,
        )

        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_not_called()
        self.bot.reminder_message_task.assert_not_called()
        self.bot.evening_message_task.assert_not_called()
        self.ctx.send.assert_called_once_with(
            "Invalid message type. Use 'morning', 'reminder', or 'evening'."
        )

    async def test_resend_with_regenerate_hint_success(self):
        """Tests resend command with regenerate_hint=True."""
        from data.readers.question import Question

        # Setup daily question
        mock_question = Question(
            question="Test question?",
            answer="Test answer",
            category="Test",
            data_source="test",
            hint="Old hint",
        )
        self.bot.game.daily_q = mock_question
        self.bot.game.daily_question_id = 1
        self.bot.game.question_selector = MagicMock()
        self.bot.game.question_selector.get_hint_from_gemini = MagicMock(
            return_value="New hint"
        )

        await self.cog.resend.callback(
            self.cog,
            self.ctx,
            message_type="reminder",
            silent=True,
            regenerate_hint=True,
        )

        self.ctx.defer.assert_called_once()
        self.bot.game.question_selector.get_hint_from_gemini.assert_called_once_with(
            mock_question
        )
        self.bot.data_manager.update_daily_question_hint.assert_called_once_with(
            1, "New hint"
        )
        self.assertEqual(self.bot.game.daily_q.hint, "New hint")
        self.bot.reminder_message_task.assert_called_once_with(silent=True)

    async def test_resend_with_regenerate_hint_no_question(self):
        """Tests resend with regenerate_hint=True when there's no active question."""
        self.bot.game.daily_q = None

        await self.cog.resend.callback(
            self.cog,
            self.ctx,
            message_type="reminder",
            silent=True,
            regenerate_hint=True,
        )

        self.ctx.defer.assert_called_once()
        self.ctx.send.assert_called_once_with(
            "Cannot regenerate hint: no active question.", ephemeral=True
        )
        self.bot.reminder_message_task.assert_not_called()

    async def test_resend_with_regenerate_hint_generation_fails(self):
        """Tests resend when hint generation returns None."""
        from data.readers.question import Question

        mock_question = Question(
            question="Test question?",
            answer="Test answer",
            category="Test",
            data_source="test",
            hint="Old hint",
        )
        self.bot.game.daily_q = mock_question
        self.bot.game.question_selector = MagicMock()
        self.bot.game.question_selector.get_hint_from_gemini = MagicMock(
            return_value=None
        )

        await self.cog.resend.callback(
            self.cog,
            self.ctx,
            message_type="reminder",
            silent=True,
            regenerate_hint=True,
        )

        self.ctx.defer.assert_called_once()
        self.ctx.send.assert_called_once_with(
            "❌ Hint generation returned empty result.", ephemeral=True
        )
        self.bot.reminder_message_task.assert_not_called()

    async def test_resend_with_regenerate_hint_exception(self):
        """Tests resend when hint generation raises an exception."""
        from data.readers.question import Question

        mock_question = Question(
            question="Test question?",
            answer="Test answer",
            category="Test",
            data_source="test",
            hint="Old hint",
        )
        self.bot.game.daily_q = mock_question
        self.bot.game.question_selector = MagicMock()
        self.bot.game.question_selector.get_hint_from_gemini = MagicMock(
            side_effect=Exception("API Error")
        )

        await self.cog.resend.callback(
            self.cog,
            self.ctx,
            message_type="reminder",
            silent=True,
            regenerate_hint=True,
        )

        self.ctx.defer.assert_called_once()
        # Check that error message contains the exception
        call_args = self.ctx.send.call_args[0][0]
        self.assertIn("❌ Error generating hint:", call_args)
        self.assertIn("API Error", call_args)
        self.bot.reminder_message_task.assert_not_called()

    async def test_refund_updates_player_data(self):
        """
        Test that the refund command correctly updates player data.
        """
        # Setup mocks
        member = MagicMock(spec=discord.Member)
        member.id = "player_id_123"
        member.display_name = "TestPlayer"
        member.mention = "@TestPlayer"

        amount = 50
        reason = "Test refund"

        # Configure the mock player_manager
        player_manager = self.bot.player_manager

        # We'll have it return a different mock each time to simulate the data changing.
        mock_player_before_refund = MagicMock()
        mock_player_after_refund = MagicMock()
        mock_player_after_refund.score = 150

        player_manager.get_or_create_player.return_value = mock_player_before_refund
        player_manager.get_player.return_value = mock_player_after_refund

        # Call the refund command
        await self.cog.refund.callback(
            self.cog, self.ctx, member, amount, reason=reason
        )

        # Assertions
        player_manager.update_score.assert_called_once_with(str(member.id), amount)
        player_manager.adjust_season_score.assert_called_once_with(
            str(member.id), amount
        )
        self.bot.data_manager.log_score_adjustment.assert_called_once_with(
            player_id=str(member.id),
            admin_id=str(self.ctx.author.id),
            amount=amount,
            reason=reason,
        )

        # Verify get_or_create_player was called
        player_manager.get_or_create_player.assert_called_once()

        # Check the final message
        expected_message = f"Refunded {member.mention}: +{amount} (Score: {mock_player_after_refund.score}). Reason: {reason}"
        self.ctx.send.assert_called_once_with(expected_message)

    async def test_refund_player_not_found_after_refund(self):
        """Test refund command when player cannot be found after refund."""
        member = MagicMock(spec=discord.Member)
        member.id = "player_id_123"
        member.display_name = "TestPlayer"

        amount = 50
        reason = "Test refund"

        player_manager = self.bot.player_manager
        mock_player_before_refund = MagicMock()
        player_manager.get_or_create_player.return_value = mock_player_before_refund
        player_manager.get_player.return_value = None  # Player not found after refund

        await self.cog.refund.callback(
            self.cog, self.ctx, member, amount, reason=reason
        )

        player_manager.update_score.assert_called_once_with(str(member.id), amount)
        player_manager.adjust_season_score.assert_called_once_with(
            str(member.id), amount
        )
        self.ctx.send.assert_called_once_with(
            f"Could not find player {member.display_name} after refund."
        )

    # Feature and sync tests removed.

    @patch("src.cogs.admin.Subscriber")
    async def test_subscribe_member(self, mock_subscriber):
        """Test subscribe command with a member."""
        member = MagicMock(spec=discord.Member)
        member.id = 123
        member.display_name = "TestMember"

        await self.cog.subscribe.callback(
            self.cog, self.ctx, subscribe=True, member=member, channel=None
        )

        self.ctx.defer.assert_called_once()
        mock_subscriber.assert_called_once()
        self.bot.game.add_subscriber.assert_called_once()
        self.ctx.send.assert_called_once_with(
            f"Subscribed {member.display_name} to daily questions."
        )

    @patch("src.cogs.admin.Subscriber")
    async def test_unsubscribe_member(self, mock_subscriber):
        """Test unsubscribe command with a member."""
        member = MagicMock(spec=discord.Member)
        member.id = 123
        member.display_name = "TestMember"

        await self.cog.subscribe.callback(
            self.cog, self.ctx, subscribe=False, member=member, channel=None
        )

        self.ctx.defer.assert_called_once()
        mock_subscriber.assert_called_once()
        self.bot.game.remove_subscriber.assert_called_once()
        self.ctx.send.assert_called_once_with(
            f"Unsubscribed {member.display_name} from daily questions."
        )

    @patch("src.cogs.admin.Subscriber")
    async def test_subscribe_channel(self, mock_subscriber):
        """Test subscribe command with a channel."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 456
        channel.name = "test-channel"

        await self.cog.subscribe.callback(
            self.cog, self.ctx, subscribe=True, member=None, channel=channel
        )

        self.ctx.defer.assert_called_once()
        mock_subscriber.assert_called_once()
        self.bot.game.add_subscriber.assert_called_once()
        self.ctx.send.assert_called_once_with(
            f"Subscribed {channel.name} to daily questions."
        )

    @patch("src.cogs.admin.Subscriber")
    async def test_unsubscribe_channel(self, mock_subscriber):
        """Test unsubscribe command with a channel."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 456
        channel.name = "test-channel"

        await self.cog.subscribe.callback(
            self.cog, self.ctx, subscribe=False, member=None, channel=channel
        )

        self.ctx.defer.assert_called_once()
        mock_subscriber.assert_called_once()
        self.bot.game.remove_subscriber.assert_called_once()
        self.ctx.send.assert_called_once_with(
            f"Unsubscribed {channel.name} from daily questions."
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


class TestAdminSeasonCommand(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.game = MagicMock()
        self.bot.data_manager = MagicMock()

        self.cog = Admin(self.bot)

        self.ctx = MagicMock()
        self.ctx.defer = AsyncMock()
        self.ctx.send = AsyncMock()
        self.ctx.author = MagicMock()

        # Default: seasons enabled, active season present, no active question
        self.bot.game.season_manager.enabled = True
        self.bot.game.daily_question_id = None

        from src.core.season import Season
        from datetime import date

        self.mock_season = Season(
            season_id=7,
            season_name="April 2026",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 30),
            is_active=True,
        )
        self.bot.game.data_manager.get_current_season.return_value = self.mock_season
        self.bot.game.season_manager.get_season_progress.return_value = (5, 30)
        self.bot.game.data_manager.get_season_scores.return_value = ["p1", "p2", "p3"]

    async def test_season_info_disabled(self):
        """Returns error when seasons are disabled."""
        self.bot.game.season_manager.enabled = False
        await self.cog.season.callback(self.cog, self.ctx)
        self.ctx.send.assert_called_once_with(
            "Seasons are not enabled.", ephemeral=True
        )

    async def test_season_info_no_active_season(self):
        """Returns error when no active season exists."""
        self.bot.game.data_manager.get_current_season.return_value = None
        await self.cog.season.callback(self.cog, self.ctx)
        self.ctx.send.assert_called_once_with("No active season found.", ephemeral=True)

    async def test_season_info_with_challenge(self):
        """Default (no flags) returns season info card including challenge name."""
        mock_challenge = MagicMock()
        mock_challenge.badge_emoji = "⚡"
        mock_challenge.challenge_name = "Speed Demon"
        self.bot.game.data_manager.get_season_challenge.return_value = mock_challenge

        await self.cog.season.callback(self.cog, self.ctx)

        self.ctx.send.assert_called_once()
        msg = self.ctx.send.call_args[0][0]
        self.assertIn("April 2026", msg)
        self.assertIn("Day 5/30", msg)
        self.assertIn("⚡ Speed Demon", msg)
        self.assertIn("3", msg)  # player count

    async def test_season_info_no_challenge(self):
        """Default (no flags) shows 'None' when no challenge is set."""
        self.bot.game.data_manager.get_season_challenge.return_value = None

        await self.cog.season.callback(self.cog, self.ctx)

        msg = self.ctx.send.call_args[0][0]
        self.assertIn("None", msg)

    async def test_season_end_no_active_question(self):
        """end:True finalizes the season and reports the next season name."""
        from src.core.season import Season
        from datetime import date

        next_season = Season(8, "May 2026", date(2026, 5, 1), date(2026, 5, 31), True)
        self.bot.game.season_manager.get_or_create_current_season.return_value = (
            next_season
        )

        await self.cog.season.callback(self.cog, self.ctx, end=True)

        self.bot.game.season_manager.finalize_season.assert_called_once_with(7)
        self.bot.game.season_manager.get_or_create_current_season.assert_called_once()
        msg = self.ctx.send.call_args[0][0]
        self.assertIn("April 2026", msg)
        self.assertIn("May 2026", msg)

    async def test_season_end_blocked_mid_day(self):
        """end:True is blocked when a question is active and force is False."""
        self.bot.game.daily_question_id = 42

        await self.cog.season.callback(self.cog, self.ctx, end=True, force=False)

        self.bot.game.season_manager.finalize_season.assert_not_called()
        msg = self.ctx.send.call_args[0][0]
        self.assertIn("A question is active", msg)

    async def test_season_end_force_mid_day(self):
        """end:True force:True proceeds and logs a warning when question is active."""
        self.bot.game.daily_question_id = 42
        from src.core.season import Season
        from datetime import date

        next_season = Season(8, "May 2026", date(2026, 5, 1), date(2026, 5, 31), True)
        self.bot.game.season_manager.get_or_create_current_season.return_value = (
            next_season
        )

        with patch("src.cogs.admin.logging") as mock_log:
            await self.cog.season.callback(self.cog, self.ctx, end=True, force=True)
            mock_log.warning.assert_called_once()

        self.bot.game.season_manager.finalize_season.assert_called_once_with(7)


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
