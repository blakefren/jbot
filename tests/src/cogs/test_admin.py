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
            self.cog, self.ctx, message_type="morning", silent=True
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
            self.cog, self.ctx, message_type="morning", silent=False
        )

        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_called_once_with(silent=False)
        self.bot.reminder_message_task.assert_not_called()
        self.bot.evening_message_task.assert_not_called()
        self.ctx.send.assert_called_once_with("Morning message resent.")

    async def test_resend_reminder_silent(self):
        """Tests resend command for reminder message with silent=True."""
        await self.cog.resend.callback(
            self.cog, self.ctx, message_type="reminder", silent=True
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
            self.cog, self.ctx, message_type="reminder", silent=False
        )

        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_not_called()
        self.bot.reminder_message_task.assert_called_once_with(silent=False)
        self.bot.evening_message_task.assert_not_called()
        self.ctx.send.assert_called_once_with("Reminder message resent.")

    async def test_resend_evening_silent(self):
        """Tests resend command for evening message with silent=True."""
        await self.cog.resend.callback(
            self.cog, self.ctx, message_type="evening", silent=True
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
            self.cog, self.ctx, message_type="evening", silent=False
        )

        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_not_called()
        self.bot.reminder_message_task.assert_not_called()
        self.bot.evening_message_task.assert_called_once_with(silent=False)
        self.ctx.send.assert_called_once_with("Evening message resent.")

    async def test_resend_invalid_message_type(self):
        """Tests resend command with an invalid message type."""
        await self.cog.resend.callback(
            self.cog, self.ctx, message_type="invalid", silent=False
        )

        self.ctx.defer.assert_called_once()
        self.bot.morning_message_task.assert_not_called()
        self.bot.reminder_message_task.assert_not_called()
        self.bot.evening_message_task.assert_not_called()
        self.ctx.send.assert_called_once_with(
            "Invalid message type. Use 'morning', 'reminder', or 'evening'."
        )

    async def test_refund_updates_player_data(self):
        """
        Test that the refund command correctly updates player data.
        """
        # Setup mocks
        member = MagicMock(spec=discord.Member)
        member.id = "player_id_123"
        member.display_name = "TestPlayer"

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
        player_manager.refund_score.assert_called_once_with(str(member.id), amount)
        self.bot.data_manager.log_score_adjustment.assert_called_once_with(
            player_id=str(member.id),
            admin_id=str(self.ctx.author.id),
            amount=amount,
            reason=reason,
        )

        # Verify get_or_create_player was called
        player_manager.get_or_create_player.assert_called_once()

        # Check the final message
        expected_message = f"Refunded {amount} to {member.display_name}. New score: {mock_player_after_refund.score}. Reason: {reason}"
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

        player_manager.refund_score.assert_called_once_with(str(member.id), amount)
        self.ctx.send.assert_called_once_with(
            f"Could not find player {member.display_name} after refund."
        )

    async def test_sync_command(self):
        """Test the sync command syncs the command tree."""
        await self.cog.sync.callback(self.cog, self.ctx)

        self.bot.tree.sync.assert_called_once()
        self.ctx.send.assert_called_once_with("Command tree synced.")

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

    async def test_feature_no_subcommand(self):
        """Test feature command with no subcommand."""
        self.ctx.invoked_subcommand = None

        await self.cog.feature.callback(self.cog, self.ctx)

        self.ctx.send.assert_called_once_with(
            "Invalid feature command. Use `enable` or `disable`."
        )

    async def test_feature_with_subcommand(self):
        """Test feature command with a subcommand (doesn't send error message)."""
        self.ctx.invoked_subcommand = MagicMock()

        await self.cog.feature.callback(self.cog, self.ctx)

        self.ctx.send.assert_not_called()

    async def test_enable_feature_fight(self):
        """Test enabling the fight feature."""
        await self.cog.enable_feature.callback(self.cog, self.ctx, feature_name="fight")

        self.bot.game.enable_manager.assert_called_once_with("fight")
        self.ctx.send.assert_called_once_with("Feature 'fight' enabled.")

    async def test_enable_feature_powerup(self):
        """Test enabling the powerup feature."""
        self.bot.player_manager.get_all_players.return_value = {
            "p1": MagicMock(),
            "p2": MagicMock(),
        }

        await self.cog.enable_feature.callback(
            self.cog, self.ctx, feature_name="powerup"
        )

        self.bot.game.enable_manager.assert_called_once_with(
            "powerup", players=["p1", "p2"]
        )
        self.ctx.send.assert_called_once_with("Feature 'powerup' enabled.")

    async def test_enable_feature_coop(self):
        """Test enabling the coop feature."""
        await self.cog.enable_feature.callback(self.cog, self.ctx, feature_name="coop")

        self.bot.game.enable_manager.assert_called_once_with("coop")
        self.ctx.send.assert_called_once_with("Feature 'coop' enabled.")

    @patch("src.cfg.main.ConfigReader")
    async def test_enable_feature_roles(self, mock_config_reader):
        """Test enabling the roles feature."""
        mock_config_instance = MagicMock()
        mock_config_reader.return_value = mock_config_instance

        await self.cog.enable_feature.callback(self.cog, self.ctx, feature_name="roles")

        self.bot.game.enable_manager.assert_called_once_with(
            "roles", db=self.bot.data_manager.db, config=mock_config_instance
        )
        self.ctx.send.assert_called_once_with("Feature 'roles' enabled.")

    async def test_disable_feature(self):
        """Test disabling a feature."""
        await self.cog.disable_feature.callback(
            self.cog, self.ctx, feature_name="fight"
        )

        self.bot.game.disable_manager.assert_called_once_with("fight")
        self.ctx.send.assert_called_once_with("Feature 'fight' disabled.")


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
