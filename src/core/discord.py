import asyncio
import datetime
import discord
import os

from discord.ext import commands, tasks
from zoneinfo import ZoneInfo


from src.cfg.main import ConfigReader
import sys

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

import logging
from src.core.data_manager import DataManager
from src.core.game_runner import GameRunner
from src.core.player_manager import PlayerManager
from data.readers.question import Question
from data.readers.question_selector import QuestionSelector


# Timezone Configuration
def parse_time(time_str: str, default_time: datetime.time) -> datetime.time:
    """Parse a time string in HH:MM format."""
    try:
        h, m = map(int, time_str.split(":"))
        return datetime.time(hour=h, minute=m)
    except (ValueError, TypeError):
        return default_time


try:
    config_reader = ConfigReader()
    TIMEZONE_STR = config_reader.get("JBOT_TIMEZONE") or "US/Pacific"
    TIMEZONE = ZoneInfo(TIMEZONE_STR)

    MORNING_TIME_STR = config_reader.get("JBOT_MORNING_TIME")
    REMINDER_TIME_STR = config_reader.get("JBOT_REMINDER_TIME")
    EVENING_TIME_STR = config_reader.get("JBOT_EVENING_TIME")

    MORNING_TIME = parse_time(
        MORNING_TIME_STR, datetime.time(hour=8, minute=0)
    ).replace(tzinfo=TIMEZONE)
    REMINDER_TIME = parse_time(
        REMINDER_TIME_STR, datetime.time(hour=19, minute=0)
    ).replace(tzinfo=TIMEZONE)
    EVENING_TIME = parse_time(
        EVENING_TIME_STR, datetime.time(hour=20, minute=0)
    ).replace(tzinfo=TIMEZONE)

except Exception as e:
    logging.error(
        f"Error reading time configuration, defaulting to hardcoded times. Error: {e}"
    )
    TIMEZONE = ZoneInfo("US/Pacific")
    MORNING_TIME = datetime.time(hour=8, minute=0, tzinfo=TIMEZONE)
    REMINDER_TIME = datetime.time(hour=19, minute=30, tzinfo=TIMEZONE)
    EVENING_TIME = datetime.time(hour=20, minute=0, tzinfo=TIMEZONE)


class DiscordBot(commands.Bot):
    """
    A concrete Discord bot implementation.
    Handles Discord-specific functionality like commands and tasks.
    """

    def __init__(
        self,
        bot_token: str,
        game: GameRunner,
        config: ConfigReader,
        player_manager: PlayerManager,
        command_prefix: str = "!",
    ):
        # discord.py specific setup
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guild_messages = True
        intents.dm_messages = True
        intents.members = True
        super().__init__(command_prefix=command_prefix, intents=intents)

        self.game = game
        self.config = config
        self.player_manager = player_manager
        self.data_manager = self.game.data_manager
        self.bot_token = bot_token
        self.ready_event_fired = False

    async def setup_hook(self):
        """This is called when the bot is setting up."""
        logging.info("setup_hook: loading cogs")
        for filename in os.listdir(os.path.join(project_root, "src", "cogs")):
            if filename.endswith(".py") and not filename.startswith("__"):
                try:
                    await self.load_extension(f"cogs.{filename[:-3]}")
                    logging.info(f"Loaded cog: {filename}")
                except Exception as e:
                    logging.error(f"Failed to load cog {filename}: {e}")

        # Sync commands after loading cogs
        try:
            logging.info("setup_hook: syncing commands start")
            await self.tree.sync()
            logging.info("setup_hook: syncing commands finish")
        except Exception as e:
            logging.error(e)

    async def run(self):
        """Starts the Discord bot."""
        await self.start(self.bot_token)

    async def on_ready(self):
        """
        Event handler that runs when the bot successfully connects to Discord.
        This is where scheduled tasks are started.
        """
        restart_file = os.path.join(project_root, "restart.inf")
        if os.path.exists(restart_file):
            try:
                with open(restart_file, "r") as f:
                    data = f.read()
                if data:
                    channel_id, author_id = data.split(",")
                    channel = self.get_channel(int(channel_id))
                    if channel:
                        author = await self.fetch_user(int(author_id))
                        if author:
                            await channel.send(f"Bot is back online, {author.mention}.")
            except Exception as e:
                logging.error(f"Error processing restart info: {e}")
            finally:
                os.remove(restart_file)

        if not self.ready_event_fired:
            logging.info(f"Logged in as {self.user} (ID: {self.user.id})")
            logging.info("------")
            self.ready_event_fired = True
        else:
            logging.info("Bot reconnected.")
        # Start the tasks
        if not self.morning_message_task.is_running():
            self.morning_message_task.start()
            logging.info(
                f"Morning message task started. Next iteration: {self.morning_message_task.next_iteration}"
            )
        if not self.reminder_message_task.is_running():
            self.reminder_message_task.start()
            logging.info(
                f"Reminder message task started. Next iteration: {self.reminder_message_task.next_iteration}"
            )
        if not self.evening_message_task.is_running():
            self.evening_message_task.start()
            logging.info(
                f"Evening message task started. Next iteration: {self.evening_message_task.next_iteration}"
            )
        # Set daily question, if bot started after the morning message.
        now = datetime.datetime.now(TIMEZONE)
        if MORNING_TIME < now.time() < EVENING_TIME and self.game.daily_q is None:
            logging.info(f"Bot started after morning message time.")
            self.game.set_daily_question()
            if not self.game.daily_q:
                logging.warning("No question found for today.")
            else:
                logging.info(
                    f"Set daily question with hash {self.game.daily_q.id} on startup."
                )

    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ):
        """Global error handler for all commands."""
        # Check if the error is a CommandInvokeError, and get the original exception
        if isinstance(error, commands.CommandInvokeError):
            error = error.original

        if isinstance(error, commands.CommandNotFound):
            # Silently ignore commands that are not found to avoid spam.
            return
        elif isinstance(error, commands.MissingRequiredArgument):
            message = f"You're missing the `{error.param.name}` argument. Try `!help {ctx.command.name}` for more info."
        elif isinstance(error, commands.BadArgument):
            message = f"I couldn't understand one of your arguments. Try `!help {ctx.command.name}` for more info."
        elif isinstance(error, (commands.NotOwner, commands.MissingPermissions)):
            message = "You don't have permission to use this command."
        elif isinstance(error, commands.CheckFailure):
            # A generic message for other checks that might fail.
            message = "You don't meet the requirements to run this command."
        else:
            # For any other errors, log them and send a generic failure message.
            logging.error(
                f"An unexpected error occurred in command '{ctx.command}': {error}"
            )
            self.data_manager.log_messaging_event(
                direction="outgoing",
                method="Discord",
                recipient_or_sender=str(ctx.author.id),
                content=f"Error in command {ctx.command}: {error}",
                status="failed",
            )
            message = "An unexpected error occurred while running the command."

        # Send the error message. We use send_message to handle both interactions and regular commands.
        await self.send_message(
            message, ctx=ctx, interaction=ctx.interaction, ephemeral=True
        )

    async def on_message(self, message):
        """
        Processes incoming messages and dispatches commands.
        """
        if message.author == self.user:
            return

        await self.process_commands(message)

    @tasks.loop(time=MORNING_TIME)
    async def morning_message_task(self, silent: bool = False):
        """Sends the morning message and question to all subscribers."""
        logging.info(
            f"Morning message task running at {datetime.datetime.now(TIMEZONE)}..."
        )
        try:
            self.game.set_daily_question()
        except Exception as e:
            self._log_task_error(e, "morning_message_task - set_daily_question")
            # If we can't set a question, there's no point in sending a message.
            return

        if not silent:
            try:
                await self._send_daily_message_to_all_subscribers(
                    self.game.get_morning_message_content,
                    "morning_message",
                    send_leaderboard=True,
                )
            except Exception as e:
                self._log_task_error(e, "morning_message_task - send_message")

    @tasks.loop(time=REMINDER_TIME)
    async def reminder_message_task(self, silent: bool = False):
        """Sends a reminder to all subscribers, tagging those who haven't guessed."""
        logging.info(
            f"Reminder message task running at {datetime.datetime.now(TIMEZONE)}..."
        )
        if not self.game.daily_q:
            logging.warning("Reminder task: No daily question set, skipping reminder.")
            return

        if not silent:
            try:
                content_getter = lambda: self.game.get_reminder_message_content(
                    self.config.get_bool("JBOT_TAG_UNANSWERED_PLAYERS")
                )
                await self._send_daily_message_to_all_subscribers(
                    content_getter, "reminder_message"
                )
            except Exception as e:
                self._log_task_error(e, "reminder_message_task")

    @tasks.loop(time=EVENING_TIME)
    async def evening_message_task(self, silent: bool = False):
        """Sends the evening answer to all subscribers."""
        logging.info(
            f"Evening message task running at {datetime.datetime.now(TIMEZONE)}..."
        )

        # 1. Update roles
        try:
            roles_cog = self.get_cog("RolesCog")
            if roles_cog:
                logging.info("Updating roles...")
                roles_cog.roles_game_mode.run()  # Update roles in DB
                for guild in self.guilds:
                    await roles_cog.apply_discord_roles(guild)
                logging.info("Roles updated.")
            else:
                logging.warning("RolesCog not found, skipping role update.")
        except Exception as e:
            self._log_task_error(e, "evening_message_task - update_roles")

        # 2. Send evening message
        if not silent:
            try:
                await self._send_daily_message_to_all_subscribers(
                    self.game.get_evening_message_content,
                    "evening_message",
                    send_leaderboard=True,
                    requires_guild=True,
                    show_daily_bonuses=True,
                )
            except Exception as e:
                self._log_task_error(e, "evening_message_task - send_message")

    async def _send_daily_message_to_all_subscribers(
        self,
        content_getter,
        success_status: str,
        send_leaderboard: bool = False,
        requires_guild: bool = False,
        show_daily_bonuses: bool = False,
    ):
        """Helper function to send a daily message to all subscribers."""
        logging.debug(f"DiscordBot._send_daily_message_to_all_subscribers")
        if not self.game.daily_q:
            logging.warning("No question available for today.")
            return

        for sub in self.game.get_subscribed_users():
            guild = None
            if sub.is_channel:
                channel = self.get_channel(sub.sub_id)
                if channel:
                    guild = channel.guild

            # Generate content
            if requires_guild:
                content = content_getter(guild=guild)
            else:
                content = content_getter()

            # Generate leaderboard if needed
            leaderboard = None
            if send_leaderboard:
                leaderboard = self.game.get_scores_leaderboard(
                    guild, show_daily_bonuses=show_daily_bonuses
                )

            await self.send_message(
                content,
                is_channel=sub.is_channel,
                target_id=sub.sub_id,
                success_status=success_status,
            )
            if leaderboard:
                await self.send_message(
                    leaderboard,
                    is_channel=sub.is_channel,
                    target_id=sub.sub_id,
                    success_status=success_status,
                )

    def _log_task_error(self, e: Exception, task_name: str):
        """Logs an error for a background task."""
        logging.error(f"An error occurred during the {task_name}: {e}")
        self.data_manager.log_messaging_event(
            direction="outgoing",
            method="Discord",
            recipient_or_sender="N/A",
            content=f"Error in {task_name}: {e}",
            status="failed",
        )

    async def send_message(
        self,
        content: str,
        is_channel: bool = False,
        target_id: int = -1,
        ctx=None,
        interaction=None,
        ephemeral=False,
        success_status="sent",
    ):
        """Sends a message to a Discord user, channel, or context. Supports ephemeral for interaction responses."""
        assert (
            target_id >= 0 or ctx is not None or interaction is not None
        ), "Either target_id, ctx, or interaction must be provided."
        try:
            if interaction is not None:
                # If responding to an interaction, support ephemeral
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        content, ephemeral=ephemeral
                    )
                else:
                    await interaction.followup.send(content, ephemeral=ephemeral)
                target_id = (
                    interaction.user.id if hasattr(interaction, "user") else target_id
                )
            elif ctx is not None:
                await ctx.send(content)
                target_id = ctx.channel.id if ctx.guild else ctx.author.id
            elif is_channel:
                channel = self.get_channel(target_id)
                if channel:
                    await channel.send(content)
            else:
                user = await self.fetch_user(target_id)
                if user:
                    await user.send(content)
            self.data_manager.log_messaging_event(
                direction="outgoing",
                method="Discord",
                recipient_or_sender=str(target_id),
                content=content,
                status=success_status,
            )
        except Exception as e:
            logging.error(f"Error sending message to {target_id}: {e}")
            self.data_manager.log_messaging_event(
                direction="outgoing",
                method="Discord",
                recipient_or_sender=str(target_id),
                content=content,
                status=f"failed - {e}",
            )


async def discord_bot_async(
    config: ConfigReader,
    questions: list[Question],
    data_manager: "DataManager",
    player_manager: "PlayerManager",
):
    """Main function to initialize and run the bot."""
    from src.core.gemini_manager import GeminiManager

    gemini_manager = None
    try:
        gemini_api_key = config.get_gemini_api_key()
        if gemini_api_key:
            gemini_manager = GeminiManager(api_key=gemini_api_key)
    except ValueError as e:
        logging.warning(f"Could not initialize GeminiManager: {e}")

    question_selector = QuestionSelector(
        questions,
        gemini_manager=gemini_manager,
    )
    game = GameRunner(question_selector, data_manager)
    game.reminder_time = REMINDER_TIME

    # Register managers
    from core.powerup import PowerUpManager
    from core.roles import RolesGameMode

    game.register_manager("powerup", PowerUpManager)
    game.register_manager("roles", RolesGameMode)

    bot = DiscordBot(config.get("JBOT_DISCORD_BOT_TOKEN"), game, config, player_manager)
    await bot.run()


def run_discord_bot(
    config: ConfigReader,
    questions: list[Question],
    data_manager: "DataManager",
    player_manager: "PlayerManager",
):
    try:
        asyncio.run(discord_bot_async(config, questions, data_manager, player_manager))
    except KeyboardInterrupt:
        logging.info("Bot shutdown requested by user.")
