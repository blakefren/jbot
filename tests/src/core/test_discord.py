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
    TIMEZONE,
    discord_bot_async,
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

    @patch("src.core.discord.os.listdir")
    async def test_setup_hook_loads_cogs_and_continues_after_load_error(
        self, mock_listdir
    ):
        mock_listdir.return_value = [
            "trivia.py",
            "broken.py",
            "__init__.py",
            "notes.txt",
        ]
        self.bot.load_extension = AsyncMock(side_effect=[None, RuntimeError("bad cog")])
        self.bot.tree.sync = AsyncMock()

        await DiscordBot.setup_hook(self.bot)

        self.assertEqual(self.bot.load_extension.await_count, 2)
        self.assertEqual(
            [call.args[0] for call in self.bot.load_extension.await_args_list],
            ["cogs.trivia", "cogs.broken"],
        )
        self.bot.tree.sync.assert_awaited_once()

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

    async def test_morning_message_task_drains_season_announcements(self):
        """Pending season announcements are broadcast before the morning message."""
        self.bot._broadcast_announcement = AsyncMock()
        self.bot.game.pending_season_announcements = ["Season ended!", "New season!"]

        await self.morning_task_coro(self.bot, silent=False)

        self.assertEqual(self.bot._broadcast_announcement.await_count, 2)
        calls = self.bot._broadcast_announcement.call_args_list
        self.assertEqual(calls[0], call("Season ended!"))
        self.assertEqual(calls[1], call("New season!"))
        # List should be cleared after draining
        self.assertEqual(self.bot.game.pending_season_announcements, [])

    async def test_morning_message_task_no_announcements_when_silent(self):
        """Season announcements are NOT sent in silent mode."""
        self.bot._broadcast_announcement = AsyncMock()
        self.bot.game.pending_season_announcements = ["Season ended!"]

        await self.morning_task_coro(self.bot, silent=True)

        self.bot._broadcast_announcement.assert_not_awaited()

    async def test_morning_message_task_announcement_error_is_logged(self):
        """A failed broadcast logs the error but does not abort remaining announcements."""
        self.bot._broadcast_announcement = AsyncMock(
            side_effect=Exception("Discord error")
        )
        self.bot.game.pending_season_announcements = ["Msg1", "Msg2"]

        await self.morning_task_coro(self.bot, silent=False)

        # Both attempted, both failed, both logged; morning message still sent
        self.assertEqual(self.bot._broadcast_announcement.await_count, 2)
        self.assertEqual(self.bot._log_task_error.call_count, 2)
        self.bot._send_daily_message_to_all_subscribers.assert_awaited_once()

    async def test_on_ready_registers_views_starts_tasks_and_sets_late_question(self):
        import datetime

        self.bot.ready_event_fired = False
        self.bot.user = MagicMock(id=123)
        self.bot.game.daily_q = None
        question = MagicMock(id="question-hash")
        self.bot.game.set_daily_question.side_effect = lambda: setattr(
            self.bot.game, "daily_q", question
        )
        task_names = (
            "prepare_daily_question_task",
            "morning_message_task",
            "reminder_message_task",
            "evening_message_task",
        )
        for task_name in task_names:
            getattr(self.bot, task_name).is_running.return_value = False

        with (
            patch("src.core.discord.os.path.exists", return_value=False),
            patch("src.core.discord.GameActionView") as view_class,
            patch(
                "src.core.discord.MORNING_TIME",
                datetime.time.min.replace(tzinfo=TIMEZONE),
            ),
            patch(
                "src.core.discord.EVENING_TIME",
                datetime.time.max.replace(tzinfo=TIMEZONE),
            ),
        ):
            await DiscordBot.on_ready(self.bot)

        view_class.assert_called_once_with(self.bot)
        self.bot.add_view.assert_called_once_with(view_class.return_value)
        for task_name in task_names:
            getattr(self.bot, task_name).start.assert_called_once()
        self.bot.game.set_daily_question.assert_called_once()
        self.assertIs(self.bot.game.daily_q, question)

    async def test_on_ready_restores_restart_announcement_and_removes_file(self):
        self.bot.ready_event_fired = True
        self.bot.user = MagicMock(id=123)
        self.bot.game.daily_q = MagicMock()
        channel = AsyncMock()
        channel.send = AsyncMock()
        user = MagicMock(mention="<@456>")
        self.bot.get_channel.return_value = channel
        self.bot.fetch_user.return_value = user
        for task_name in (
            "prepare_daily_question_task",
            "morning_message_task",
            "reminder_message_task",
            "evening_message_task",
        ):
            getattr(self.bot, task_name).is_running.return_value = True

        with (
            patch("src.core.discord.os.path.exists", return_value=True),
            patch("src.core.discord.os.remove") as remove,
            patch("builtins.open", unittest.mock.mock_open(read_data="123,456")),
            patch("src.core.discord.GameActionView"),
        ):
            await DiscordBot.on_ready(self.bot)

        self.bot.get_channel.assert_called_once_with(123)
        self.bot.fetch_user.assert_awaited_once_with(456)
        channel.send.assert_awaited_once_with("Bot is back online, <@456>.")
        remove.assert_called_once()

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

    async def test_reminder_message_task_regenerates_hint_when_missing(self):
        """Verify the reminder task attempts hint regeneration when hint is None."""
        mock_question = MagicMock()
        mock_question.hint = None
        self.bot.game.daily_q = mock_question
        self.bot.game.regenerate_hint_if_missing = MagicMock(return_value=True)

        await self.reminder_task_coro(self.bot, silent=False)

        self.bot.game.regenerate_hint_if_missing.assert_called_once()
        self.bot._send_daily_message_to_all_subscribers.assert_awaited_once()

    async def test_reminder_message_task_skips_regen_when_hint_present(self):
        """Verify the reminder task skips hint regeneration when hint is already set."""
        mock_question = MagicMock()
        mock_question.hint = "Existing hint"
        self.bot.game.daily_q = mock_question
        self.bot.game.regenerate_hint_if_missing = MagicMock()

        await self.reminder_task_coro(self.bot, silent=False)

        self.bot.game.regenerate_hint_if_missing.assert_not_called()
        self.bot._send_daily_message_to_all_subscribers.assert_awaited_once()

    async def test_reminder_message_task_regen_exception_logged(self):
        """Verify that a failure in hint regeneration is logged and task continues."""
        mock_question = MagicMock()
        mock_question.hint = None
        self.bot.game.daily_q = mock_question
        self.bot.game.regenerate_hint_if_missing = MagicMock(
            side_effect=Exception("Regen error")
        )

        await self.reminder_task_coro(self.bot, silent=False)

        self.bot._log_task_error.assert_called_once()
        # The reminder message should still be sent despite the regen failure
        self.bot._send_daily_message_to_all_subscribers.assert_awaited_once()

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

        self.bot.game.apply_crowd_wisdom_bonus.assert_called_once()
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

    @patch("src.core.discord.RolesGameMode")
    @patch("src.core.discord.logging.info")
    async def test_evening_task_does_not_report_skipped_verification_as_success(
        self, mock_info, _mock_roles_game_mode_cls
    ):
        self.bot.game.daily_question_id = 1
        self.bot.game.verify_daily_play.return_value = None

        await self.evening_task_coro(self.bot, silent=True)

        info_messages = [str(call.args[0]) for call in mock_info.call_args_list]
        self.assertFalse(
            any("all scores verified OK" in message for message in info_messages)
        )
        self.bot.game.format_verify_report.assert_not_called()
        self.bot._notify_admins.assert_not_awaited()

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

    @patch("src.core.discord.RolesGameMode")
    async def test_evening_task_calls_backup(self, mock_roles_cls):
        """Verify the evening task calls _backup_database after ending the game."""
        await self.evening_task_coro(self.bot, silent=True)
        self.bot._backup_database.assert_called_once()

    @patch("src.core.discord.RolesGameMode")
    async def test_evening_task_backup_failure_is_logged(self, mock_roles_cls):
        """Verify a backup failure is logged but does not crash the task."""
        self.bot._backup_database.side_effect = Exception("disk full")
        await self.evening_task_coro(self.bot, silent=True)
        self.bot._log_task_error.assert_called()
        call_args = self.bot._log_task_error.call_args[0]
        self.assertIn("backup", call_args[1])
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

    async def test_send_message_failure_is_logged(self):
        self.bot.fetch_user.side_effect = RuntimeError("Discord unavailable")

        await self.bot.send_message("Hello", target_id=123)

        self.bot.data_manager.log_messaging_event.assert_called_once_with(
            direction="outgoing",
            method="Discord",
            recipient_or_sender="123",
            content="Hello",
            status="failed - Discord unavailable",
        )

    async def test_notify_admins_skips_bad_ids_and_sends_valid_ids(self):
        self.bot.config.get.return_value = "123, bad-id, 456"
        self.bot.send_message = AsyncMock()

        await DiscordBot._notify_admins(self.bot, "Important update")

        self.assertEqual(self.bot.send_message.await_count, 2)
        self.bot.send_message.assert_any_await(
            "Important update",
            is_channel=False,
            target_id=123,
            success_status="admin_alert",
        )
        self.bot.send_message.assert_any_await(
            "Important update",
            is_channel=False,
            target_id=456,
            success_status="admin_alert",
        )

    async def test_send_message_to_channel(self):
        """Test sending a message to a channel by ID."""
        mock_channel = AsyncMock()
        self.bot.get_channel.return_value = mock_channel

        await self.bot.send_message("Hello Channel", is_channel=True, target_id=456)

        self.bot.get_channel.assert_called_once_with(456)
        mock_channel.send.assert_awaited_once_with("Hello Channel", view=None)
        self.bot.data_manager.log_messaging_event.assert_called_once()

    async def test_send_message_via_ctx(self):
        """Test sending a message via context."""
        mock_ctx = AsyncMock()
        mock_ctx.guild = True
        mock_ctx.channel.id = 789

        await self.bot.send_message("Hello Ctx", ctx=mock_ctx)

        mock_ctx.send.assert_awaited_once_with("Hello Ctx", view=None)
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
                    view=None,
                ),
                call(
                    "Daily Content",
                    is_channel=True,
                    target_id=2,
                    success_status="test_status",
                    view=None,
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
                    view=None,
                ),
                call(
                    "<@&12345>\nDaily Content",
                    is_channel=True,
                    target_id=2,
                    success_status="test_status",
                    view=None,
                ),
            ]
        )

    async def test_send_daily_message_with_leaderboard(self):
        """Test sending daily message with leaderboard; uses get_active_leaderboard."""
        sub1 = Subscriber(sub_id=1, is_channel=False, display_name="User1")
        self.bot.game.get_subscribed_users.return_value = {sub1}
        self.bot.game.daily_q = MagicMock()
        self.bot.game.get_active_leaderboard.return_value = "Leaderboard Content"

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
                    view=None,
                ),
                call(
                    "Leaderboard Content",
                    is_channel=False,
                    target_id=1,
                    success_status="test_status",
                    view=None,
                ),
            ]
        )

    async def test_send_daily_message_leaderboard_is_season_aware_when_seasons_enabled(
        self,
    ):
        """When seasons are enabled the broadcast calls get_active_leaderboard, not get_scores_leaderboard."""
        sub1 = Subscriber(sub_id=1, is_channel=False, display_name="User1")
        self.bot.game.get_subscribed_users.return_value = {sub1}
        self.bot.game.daily_q = MagicMock()
        self.bot.game.get_active_leaderboard.return_value = "Season LB"

        self.bot.send_message = AsyncMock()
        content_getter = MagicMock(return_value="Content")

        await self.bot._send_daily_message_to_all_subscribers(
            content_getter, "morning_message", send_leaderboard=True
        )

        self.bot.game.get_active_leaderboard.assert_called_once()
        self.bot.game.get_scores_leaderboard.assert_not_called()

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

    async def test_on_command_error_bad_argument_and_permission_branches(self):
        from discord.ext import commands

        ctx = MagicMock()
        ctx.command.name = "test_cmd"
        self.bot.send_message = AsyncMock()
        self.bot.on_command_error = DiscordBot.on_command_error.__get__(
            self.bot, DiscordBot
        )

        await self.bot.on_command_error(ctx, commands.BadArgument("bad value"))
        self.assertIn("couldn't understand", self.bot.send_message.await_args.args[0])

        self.bot.send_message.reset_mock()
        await self.bot.on_command_error(ctx, commands.CheckFailure())
        self.assertIn(
            "don't meet the requirements", self.bot.send_message.await_args.args[0]
        )

    async def test_on_command_error_unexpected_failure_is_logged(self):
        from discord.ext import commands

        ctx = MagicMock()
        ctx.command.name = "test_cmd"
        ctx.author.id = 42
        self.bot.send_message = AsyncMock()
        self.bot.on_command_error = DiscordBot.on_command_error.__get__(
            self.bot, DiscordBot
        )

        await self.bot.on_command_error(
            ctx, commands.CommandInvokeError(RuntimeError("storage failure"))
        )

        self.assertIn("unexpected error", self.bot.send_message.await_args.args[0])
        self.bot.data_manager.log_messaging_event.assert_called_once()

    @patch("src.core.discord.DiscordBot")
    @patch("src.core.discord.GameRunner")
    @patch("src.core.discord.QuestionSelector")
    @patch("src.core.gemini_manager.GeminiManager")
    async def test_discord_bot_async_builds_gemini_backed_runtime(
        self, mock_gemini, mock_selector, mock_game, mock_bot
    ):
        config = MagicMock()
        config.get_gemini_api_key.return_value = "test-key"
        config.get.side_effect = lambda key, default=None: {
            "GEMINI_MODEL": "test-model",
            "GEMINI_FALLBACK_MODEL": "fallback-model",
            "JBOT_DISCORD_BOT_TOKEN": "test-token",
        }.get(key, default)
        config.parse_question_sources.return_value = ["source"]
        mock_bot.return_value.run = AsyncMock()
        data_manager = MagicMock()
        player_manager = MagicMock()

        await discord_bot_async(config, data_manager, player_manager)

        mock_gemini.assert_called_once_with(
            api_key="test-key", model="test-model", fallback_model="fallback-model"
        )
        mock_selector.assert_called_once_with(
            sources=["source"], gemini_manager=mock_gemini.return_value
        )
        mock_game.assert_called_once_with(
            mock_selector.return_value, data_manager, player_manager
        )
        mock_bot.assert_called_once_with(
            "test-token", mock_game.return_value, config, player_manager
        )
        mock_bot.return_value.run.assert_awaited_once()

    @patch("src.core.discord.DiscordBot")
    @patch("src.core.discord.GameRunner")
    @patch("src.core.discord.QuestionSelector")
    @patch("src.core.gemini_manager.GeminiManager")
    async def test_discord_bot_async_continues_without_gemini_key(
        self, mock_gemini, mock_selector, mock_game, mock_bot
    ):
        config = MagicMock()
        config.get_gemini_api_key.side_effect = ValueError("missing key")
        config.get.return_value = "test-token"
        config.parse_question_sources.return_value = []
        mock_bot.return_value.run = AsyncMock()

        await discord_bot_async(config, MagicMock(), MagicMock())

        mock_gemini.assert_not_called()
        mock_selector.assert_called_once_with(sources=[], gemini_manager=None)
        mock_bot.return_value.run.assert_awaited_once()


class TestDiscordBotBackup(unittest.TestCase):
    """Tests for the _backup_database() helper on DiscordBot."""

    def setUp(self):
        self.bot = MagicMock(spec=DiscordBot)
        self.bot.config = MagicMock()
        self.bot.data_manager = MagicMock()

    def test_creates_backup_dir_and_calls_backup_with_dated_filename(self):
        """_backup_database() creates backups/ next to the DB and passes a dated path to data_manager."""
        import datetime
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "jbot.db")
            self.bot.data_manager.db.db_path = db_path
            self.bot.config.get.return_value = "30"
            DiscordBot._backup_database(self.bot)

            backup_dir = os.path.join(tmpdir, "backups")
            self.assertTrue(os.path.isdir(backup_dir))
            self.bot.data_manager.backup_database.assert_called_once()
            call_path = self.bot.data_manager.backup_database.call_args[0][0]
            today_str = datetime.datetime.now(TIMEZONE).strftime("%Y-%m-%d")
            self.assertEqual(
                call_path, os.path.join(backup_dir, f"jbot_{today_str}.db")
            )

    def test_prunes_old_backup_files(self):
        """_backup_database() removes backup files beyond the retention window."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = os.path.join(tmpdir, "backups")
            os.makedirs(backup_dir)

            # Create an ancient backup (should be pruned) and a future-dated one (keep)
            old_file = os.path.join(backup_dir, "jbot_2020-01-01.db")
            future_file = os.path.join(backup_dir, "jbot_2099-01-01.db")
            open(old_file, "w").close()
            open(future_file, "w").close()

            self.bot.data_manager.db.db_path = os.path.join(tmpdir, "jbot.db")
            self.bot.config.get.return_value = "30"
            DiscordBot._backup_database(self.bot)

            self.assertFalse(os.path.exists(old_file))
            self.assertTrue(os.path.exists(future_file))

    def test_non_backup_files_in_dir_are_not_touched(self):
        """_backup_database() ignores files that don't match the backup naming pattern."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = os.path.join(tmpdir, "backups")
            os.makedirs(backup_dir)

            other_file = os.path.join(backup_dir, "readme.txt")
            open(other_file, "w").close()

            self.bot.data_manager.db.db_path = os.path.join(tmpdir, "jbot.db")
            self.bot.config.get.return_value = "30"
            DiscordBot._backup_database(self.bot)

            self.assertTrue(os.path.exists(other_file))


if __name__ == "__main__":
    unittest.main()
