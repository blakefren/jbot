# tests/src/core/test_discord.py
import unittest
from unittest.mock import MagicMock, AsyncMock, patch, call

import sys
import os

# Add the project root to the Python path
project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
sys.path.insert(0, project_root)

from src.core.discord import (
    DiscordBot,
    MORNING_TIME,
    REMINDER_TIME,
    EVENING_TIME,
    PREP_TIME,
)
from src.core.subscriber import Subscriber


class TestDiscordBotTasks(unittest.IsolatedAsyncioTestCase):
    def test_time_configuration(self):
        """Verify that PREP_TIME is 10 minutes before MORNING_TIME."""
        import datetime

        # We need to act carefully with times because they might be date-aware or naive depending on setup
        # But here they should both come from the same config logic

        # Combine with a dummy date to do arithmetic
        dummy_date = datetime.date(2023, 1, 1)
        morning_dt = datetime.datetime.combine(dummy_date, MORNING_TIME)
        prep_dt = datetime.datetime.combine(dummy_date, PREP_TIME)

        # Adjust for crossing midnight backwards if necessary (e.g. morning 00:05, prep 23:55)
        if prep_dt > morning_dt:
            prep_dt -= datetime.timedelta(days=1)

        diff = morning_dt - prep_dt
        self.assertEqual(
            diff.total_seconds(),
            600,
            "PREP_TIME should be 10 minutes before MORNING_TIME",
        )

    def setUp(self):
        # Create a mock for the bot instance
        self.bot = MagicMock(spec=DiscordBot)
        self.bot.game = MagicMock()
        self.bot.guilds = [MagicMock()]
        self.bot.get_cog = MagicMock()
        self.bot.config = MagicMock()
        self.bot.data_manager = MagicMock()
        self.bot._log_task_error = MagicMock()
        self.bot._send_daily_message_to_all_subscribers = AsyncMock()
        self.bot.apply_discord_roles = AsyncMock()

        # Get coroutines from the tasks
        self.prep_task_coro = DiscordBot.prepare_daily_question_task.coro
        self.morning_task_coro = DiscordBot.morning_message_task.coro
        self.reminder_task_coro = DiscordBot.reminder_message_task.coro
        self.evening_task_coro = DiscordBot.evening_message_task.coro

    # --- Morning Task Tests ---

    async def test_prepare_daily_question_task_success(self):
        """Verify the prep task runs successfully."""
        await self.prep_task_coro(self.bot)
        self.bot.game.set_daily_question.assert_called_once()
        self.bot._log_task_error.assert_not_called()

    async def test_prepare_daily_question_task_failure(self):
        """Verify the prep task handles exceptions."""
        self.bot.game.set_daily_question.side_effect = Exception("Prep error")
        await self.prep_task_coro(self.bot)
        self.bot.game.set_daily_question.assert_called_once()
        self.bot._log_task_error.assert_called_once()

    async def test_morning_message_task_success(self):
        """Verify the morning task runs successfully."""
        await self.morning_task_coro(self.bot, silent=False)
        self.bot.game.set_daily_question.assert_called_once()
        self.bot._send_daily_message_to_all_subscribers.assert_awaited_once()
        self.bot._log_task_error.assert_not_called()

    async def test_morning_message_task_silent(self):
        """Verify the morning task does not send messages when silent."""
        await self.morning_task_coro(self.bot, silent=True)
        self.bot.game.set_daily_question.assert_called_once()
        self.bot._send_daily_message_to_all_subscribers.assert_not_awaited()

    async def test_morning_message_task_set_question_fails(self):
        """Verify task handles failure in setting the daily question."""
        self.bot.game.set_daily_question.side_effect = Exception("DB error")
        await self.morning_task_coro(self.bot, silent=False)
        self.bot.game.set_daily_question.assert_called_once()
        self.bot._log_task_error.assert_called_once()
        self.bot._send_daily_message_to_all_subscribers.assert_not_awaited()

    async def test_morning_message_task_send_message_fails(self):
        """Verify task handles failure in sending the message."""
        self.bot._send_daily_message_to_all_subscribers.side_effect = Exception(
            "Discord API error"
        )
        await self.morning_task_coro(self.bot, silent=False)
        self.bot.game.set_daily_question.assert_called_once()
        self.bot._send_daily_message_to_all_subscribers.assert_awaited_once()
        self.bot._log_task_error.assert_called_once()

    # --- Reminder Task Tests ---

    async def test_reminder_message_task_success(self):
        """Verify the reminder task runs successfully."""
        self.bot.game.daily_q = MagicMock()  # Question is set
        await self.reminder_task_coro(self.bot, silent=False)
        self.bot._send_daily_message_to_all_subscribers.assert_awaited_once()
        self.bot._log_task_error.assert_not_called()

    async def test_reminder_message_task_silent(self):
        """Verify the reminder task does not send messages when silent."""
        self.bot.game.daily_q = MagicMock()
        await self.reminder_task_coro(self.bot, silent=True)
        self.bot._send_daily_message_to_all_subscribers.assert_not_awaited()

    async def test_reminder_message_task_no_question(self):
        """Verify the reminder task skips if no question is set."""
        self.bot.game.daily_q = None
        await self.reminder_task_coro(self.bot, silent=False)
        self.bot._send_daily_message_to_all_subscribers.assert_not_awaited()
        self.bot._log_task_error.assert_not_called()

    async def test_reminder_message_task_send_fails(self):
        """Verify the reminder task logs an error if sending fails."""
        self.bot.game.daily_q = MagicMock()
        self.bot._send_daily_message_to_all_subscribers.side_effect = Exception(
            "Network error"
        )
        await self.reminder_task_coro(self.bot, silent=False)
        self.bot._send_daily_message_to_all_subscribers.assert_awaited_once()
        self.bot._log_task_error.assert_called_once()

    # --- Evening Task Tests ---

    @patch("src.core.discord.RolesGameMode")
    async def test_evening_message_task_success(self, mock_roles_game_mode_cls):
        """Verify the evening task runs all steps successfully."""
        mock_roles_instance = mock_roles_game_mode_cls.return_value

        # Mock PowerUpManager (no check_shield_usage any more)
        mock_powerup_manager = MagicMock(spec=[])
        self.bot.game.managers = {"powerup": mock_powerup_manager}

        # Mock get_evening_message_content
        self.bot.game.get_evening_message_content.return_value = "Evening Message"

        await self.evening_task_coro(self.bot, silent=False)

        mock_roles_game_mode_cls.assert_called_once_with(
            self.bot.data_manager, self.bot.config
        )
        mock_roles_instance.run.assert_called_once()
        self.bot.apply_discord_roles.assert_awaited()

        # Verify message sending
        self.bot._send_daily_message_to_all_subscribers.assert_awaited_once()

        # Verify the content passed to the sender includes the evening message
        call_args = self.bot._send_daily_message_to_all_subscribers.call_args
        content_getter = call_args[0][0]

        content = content_getter()
        self.assertIn("Evening Message", content)

        self.bot._log_task_error.assert_not_called()

    async def test_evening_message_task_update_scores_fails(self):
        """Verify task stops if updating scores fails."""
        # This test is no longer relevant as update_scores is removed
        pass

    @patch("src.core.discord.RolesGameMode")
    async def test_evening_message_task_update_roles_fails(
        self, mock_roles_game_mode_cls
    ):
        """Verify task continues if updating roles fails."""
        mock_roles_instance = mock_roles_game_mode_cls.return_value
        mock_roles_instance.run.side_effect = Exception("Role DB error")

        await self.evening_task_coro(self.bot, silent=False)

        mock_roles_instance.run.assert_called_once()
        self.bot._log_task_error.assert_called_once()
        # Message sending should still happen
        self.bot._send_daily_message_to_all_subscribers.assert_awaited_once()

    @patch("src.core.discord.RolesGameMode")
    async def test_evening_message_task_send_message_fails(
        self, mock_roles_game_mode_cls
    ):
        """Verify task logs error if sending the evening message fails."""
        self.bot._send_daily_message_to_all_subscribers.side_effect = Exception(
            "Final message error"
        )
        await self.evening_task_coro(self.bot, silent=False)

        mock_roles_game_mode_cls.assert_called_once()
        self.bot._send_daily_message_to_all_subscribers.assert_awaited_once()
        # The final error should be logged
        self.bot._log_task_error.assert_called_once()


class TestDiscordBotMethods(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock(spec=DiscordBot)
        self.bot.game = MagicMock()
        self.bot.data_manager = MagicMock()
        self.bot.config = MagicMock()
        self.bot.fetch_user = AsyncMock()
        self.bot.get_channel = MagicMock()

        # Bind the methods we want to test to the mock object
        self.bot.send_message = DiscordBot.send_message.__get__(self.bot, DiscordBot)
        self.bot._send_daily_message_to_all_subscribers = (
            DiscordBot._send_daily_message_to_all_subscribers.__get__(
                self.bot, DiscordBot
            )
        )

    async def test_send_message_to_user(self):
        """Test sending a message to a user by ID."""
        mock_user = AsyncMock()
        self.bot.fetch_user.return_value = mock_user

        await self.bot.send_message("Hello", target_id=123)

        self.bot.fetch_user.assert_awaited_once_with(123)
        mock_user.send.assert_awaited_once_with("Hello")
        self.bot.data_manager.log_messaging_event.assert_called_once()

    async def test_send_message_to_channel(self):
        """Test sending a message to a channel by ID."""
        mock_channel = AsyncMock()
        self.bot.get_channel.return_value = mock_channel

        await self.bot.send_message("Hello Channel", is_channel=True, target_id=456)

        self.bot.get_channel.assert_called_once_with(456)
        mock_channel.send.assert_awaited_once_with("Hello Channel")
        self.bot.data_manager.log_messaging_event.assert_called_once()

    async def test_send_message_via_ctx(self):
        """Test sending a message via context."""
        mock_ctx = AsyncMock()
        mock_ctx.guild = True
        mock_ctx.channel.id = 789

        await self.bot.send_message("Hello Ctx", ctx=mock_ctx)

        mock_ctx.send.assert_awaited_once_with("Hello Ctx")
        self.bot.data_manager.log_messaging_event.assert_called_once()

    async def test_send_message_via_interaction_response(self):
        """Test sending a message via interaction response."""
        mock_interaction = AsyncMock()
        mock_interaction.response.is_done = MagicMock(return_value=False)
        mock_interaction.user.id = 101

        await self.bot.send_message("Hello Interaction", interaction=mock_interaction)

        mock_interaction.response.send_message.assert_awaited_once_with(
            "Hello Interaction", ephemeral=False
        )
        self.bot.data_manager.log_messaging_event.assert_called_once()

    async def test_send_message_via_interaction_followup(self):
        """Test sending a message via interaction followup."""
        mock_interaction = AsyncMock()
        mock_interaction.response.is_done = MagicMock(return_value=True)
        mock_interaction.user.id = 101

        await self.bot.send_message("Hello Followup", interaction=mock_interaction)

        mock_interaction.followup.send.assert_awaited_once_with(
            "Hello Followup", ephemeral=False
        )
        self.bot.data_manager.log_messaging_event.assert_called_once()

    async def test_send_daily_message_to_all_subscribers(self):
        """Test sending daily message to all subscribers."""
        # Setup subscribers
        sub1 = Subscriber(sub_id=1, is_channel=False, display_name="User1")
        sub2 = Subscriber(sub_id=2, is_channel=True, display_name="Channel1")
        self.bot.game.get_subscribed_users.return_value = {sub1, sub2}
        self.bot.game.daily_q = MagicMock()
        self.bot.config.get.return_value = None  # No player role name

        # Mock send_message to avoid actual calls (we are testing the loop logic)
        self.bot.send_message = AsyncMock()

        content_getter = MagicMock(return_value="Daily Content")

        # Bind the real method to the mock bot
        self.bot._send_daily_message_to_all_subscribers = (
            DiscordBot._send_daily_message_to_all_subscribers.__get__(
                self.bot, DiscordBot
            )
        )

        await self.bot._send_daily_message_to_all_subscribers(
            content_getter, "test_status"
        )

        self.assertEqual(self.bot.send_message.await_count, 2)
        self.bot.send_message.assert_has_awaits(
            [
                call(
                    "Daily Content",
                    is_channel=False,
                    target_id=1,
                    success_status="test_status",
                ),
                call(
                    "Daily Content",
                    is_channel=True,
                    target_id=2,
                    success_status="test_status",
                ),
            ]
        )

    async def test_send_daily_message_with_player_tag(self):
        """Test sending daily message with player role tag."""
        # Setup subscribers
        sub1 = Subscriber(sub_id=1, is_channel=False, display_name="User1")
        sub2 = Subscriber(sub_id=2, is_channel=True, display_name="Channel1")
        self.bot.game.get_subscribed_users.return_value = {sub1, sub2}
        self.bot.game.daily_q = MagicMock()

        # Mock config to return a role name
        self.bot.config.get.return_value = "players"

        # Mock channel and role
        mock_channel = MagicMock()
        mock_role = MagicMock()
        mock_role.mention = "<@&12345>"
        mock_channel.guild.roles = [mock_role]
        # discord.utils.get is used, so we need to mock it or ensure the list works
        # Since we are using discord.utils.get(guild.roles, name=player_role_name)
        mock_role.name = "players"

        self.bot.get_channel.return_value = mock_channel
        self.bot.send_message = AsyncMock()

        content_getter = MagicMock(return_value="Daily Content")

        # Bind the real method to the mock bot
        self.bot._send_daily_message_to_all_subscribers = (
            DiscordBot._send_daily_message_to_all_subscribers.__get__(
                self.bot, DiscordBot
            )
        )

        await self.bot._send_daily_message_to_all_subscribers(
            content_getter, "test_status"
        )

        self.assertEqual(self.bot.send_message.await_count, 2)
        self.bot.send_message.assert_has_awaits(
            [
                call(
                    "Daily Content",
                    is_channel=False,
                    target_id=1,
                    success_status="test_status",
                ),
                call(
                    "<@&12345>\nDaily Content",
                    is_channel=True,
                    target_id=2,
                    success_status="test_status",
                ),
            ]
        )

    async def test_send_daily_message_with_leaderboard(self):
        """Test sending daily message with leaderboard."""
        sub1 = Subscriber(sub_id=1, is_channel=False, display_name="User1")
        self.bot.game.get_subscribed_users.return_value = {sub1}
        self.bot.game.daily_q = MagicMock()
        self.bot.game.get_scores_leaderboard.return_value = "Leaderboard Content"

        self.bot.send_message = AsyncMock()
        content_getter = MagicMock(return_value="Daily Content")

        await self.bot._send_daily_message_to_all_subscribers(
            content_getter, "test_status", send_leaderboard=True
        )

        self.assertEqual(self.bot.send_message.await_count, 2)
        self.bot.send_message.assert_has_awaits(
            [
                call(
                    "Daily Content",
                    is_channel=False,
                    target_id=1,
                    success_status="test_status",
                ),
                call(
                    "Leaderboard Content",
                    is_channel=False,
                    target_id=1,
                    success_status="test_status",
                ),
            ]
        )

    async def test_on_message_ignore_bot(self):
        """Test that on_message ignores messages from the bot itself."""
        self.bot.user = MagicMock()
        message = MagicMock()
        message.author = self.bot.user

        # Bind on_message
        self.bot.on_message = DiscordBot.on_message.__get__(self.bot, DiscordBot)
        self.bot.process_commands = AsyncMock()

        await self.bot.on_message(message)

        self.bot.process_commands.assert_not_called()

    async def test_on_message_process_commands(self):
        """Test that on_message processes commands for other users."""
        self.bot.user = MagicMock()
        message = MagicMock()
        message.author = MagicMock()  # Not the bot
        self.bot.process_commands = AsyncMock()

        # Bind on_message
        self.bot.on_message = DiscordBot.on_message.__get__(self.bot, DiscordBot)

        await self.bot.on_message(message)

        self.bot.process_commands.assert_awaited_once_with(message)

    async def test_on_command_error_missing_arg(self):
        """Test handling of MissingRequiredArgument error."""
        from discord.ext import commands

        ctx = MagicMock()
        ctx.command.name = "test_cmd"
        # Create a mock param with a name attribute
        mock_param = MagicMock()
        mock_param.name = "arg1"
        error = commands.MissingRequiredArgument(mock_param)

        self.bot.send_message = AsyncMock()
        self.bot.on_command_error = DiscordBot.on_command_error.__get__(
            self.bot, DiscordBot
        )

        await self.bot.on_command_error(ctx, error)

        self.bot.send_message.assert_awaited_once()
        args, kwargs = self.bot.send_message.call_args
        self.assertIn("missing the `arg1` argument", args[0])

    async def test_on_command_error_command_not_found(self):
        """Test handling of CommandNotFound error."""
        from discord.ext import commands

        ctx = MagicMock()
        error = commands.CommandNotFound()

        self.bot.send_message = AsyncMock()
        self.bot.on_command_error = DiscordBot.on_command_error.__get__(
            self.bot, DiscordBot
        )

        await self.bot.on_command_error(ctx, error)

        self.bot.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
