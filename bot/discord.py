from modes.powerup import PowerUpManager
import asyncio
import datetime
import discord
import os
import sys

from discord.ext import commands, tasks
from zoneinfo import ZoneInfo

from bot.subscriber import Subscriber
from cfg.main import ConfigReader
from database.logger import Logger
from modes.game_runner import GameRunner
from readers.question import Question
from readers.question_selector import QuestionSelector

# TODO: read timezone from config
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
        command_prefix: str = "!",
    ):
        # discord.py specific setup
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guild_messages = True
        intents.dm_messages = True
        super().__init__(command_prefix=command_prefix, intents=intents)

        self.game = game
        self.config = config
        self.logger = self.game.logger
        self.bot_token = bot_token
        self.ready_event_fired = False

    async def setup_hook(self):
        """This is called when the bot is setting up."""
        print("setup_hook: loading cogs")
        for filename in os.listdir(os.path.join([".", "bot", "cogs"])):
            if filename.endswith(".py") and not filename.startswith("__"):
                try:
                    await self.load_extension(f"bot.cogs.{filename[:-3]}")
                    print(f"Loaded cog: {filename}")
                except Exception as e:
                    print(f"Failed to load cog {filename}: {e}")

        # Sync commands after loading cogs
        try:
            print("setup_hook: syncing commands start")
            await self.tree.sync()
            print("setup_hook: syncing commands finish")
        except Exception as e:
            print(e)

    async def run(self):
        """Starts the Discord bot."""
        await self.start(self.bot_token)

    async def on_ready(self):
        """
        Event handler that runs when the bot successfully connects to Discord.
        This is where scheduled tasks are started.
        """
        if os.path.exists("restart.inf"):
            try:
                with open("restart.inf", "r") as f:
                    data = f.read()
                if data:
                    channel_id, author_id = data.split(",")
                    channel = self.get_channel(int(channel_id))
                    if channel:
                        author = await self.fetch_user(int(author_id))
                        if author:
                            await channel.send(f"Bot is back online, {author.mention}.")
            except Exception as e:
                print(f"Error processing restart info: {e}")
            finally:
                os.remove("restart.inf")

        if not self.ready_event_fired:
            print(f"Logged in as {self.user} (ID: {self.user.id})")
            self.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender=str(self.user.id),
                content=f"Bot logged in as {self.user.name}",
                status="success",
            )
            print("------")
            self.ready_event_fired = True
        else:
            print("Bot reconnected.")
            self.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender=str(self.user.id),
                content="Bot reconnected.",
                status="success",
            )
        # Start the tasks
        if not self.morning_message_task.is_running():
            self.morning_message_task.start()
            print(
                f"Morning message task started. Next iteration: {self.morning_message_task.next_iteration}"
            )
        if not self.reminder_message_task.is_running():
            self.reminder_message_task.start()
            print(
                f"Reminder message task started. Next iteration: {self.reminder_message_task.next_iteration}"
            )
        if not self.evening_message_task.is_running():
            self.evening_message_task.start()
            print(
                f"Evening message task started. Next iteration: {self.evening_message_task.next_iteration}"
            )
        # Set daily question, if bot started after the morning message but before the evening message.
        now = datetime.datetime.now(TIMEZONE)
        if MORNING_TIME < now.time() < EVENING_TIME and self.game.daily_q is None:
            print("Bot started after morning message time. Setting daily question.")
            self.game.set_daily_question()
            if not self.game.daily_q:
                print("No question found for today.")

    async def on_message(self, message):
        """
        Processes incoming messages and dispatches commands.
        """
        if message.author == self.user:
            return

        print(f"Received message from {message.author}: {message.content}")
        self.logger.log_messaging_event(
            direction="from",
            method="Discord",
            recipient_or_sender=str(message.author.id),
            content=message.content,
            status="received",
        )
        await self.process_commands(message)

    @tasks.loop(time=MORNING_TIME)
    async def morning_message_task(self):
        """Sends the morning message and question to all subscribers."""
        print(f"Morning message task running at {datetime.datetime.now(TIMEZONE)}...")
        try:
            self.game.set_daily_question()
            await self._send_daily_message_to_all_subscribers(
                self.game.get_morning_message_content, "morning_message"
            )
        except Exception as e:
            self._log_task_error(e, "morning_message_task")

    @tasks.loop(time=REMINDER_TIME)
    async def reminder_message_task(self):
        """Sends a reminder to all subscribers, tagging those who haven't guessed."""
        print(f"Reminder message task running at {datetime.datetime.now(TIMEZONE)}...")
        try:
            content_getter = lambda: self.game.get_reminder_message_content(
                self.config.get_bool("TAG_UNANSWERED_PLAYERS")
            )
            await self._send_daily_message_to_all_subscribers(
                content_getter, "reminder_message"
            )
        except Exception as e:
            self._log_task_error(e, "reminder_message_task")

    @tasks.loop(time=EVENING_TIME)
    async def evening_message_task(self):
        """Sends the evening answer to all subscribers."""
        print(f"Evening message task running at {datetime.datetime.now(TIMEZONE)}...")
        try:
            await self._send_daily_message_to_all_subscribers(
                self.game.get_evening_message_content, "evening_message"
            )
        except Exception as e:
            self._log_task_error(e, "evening_message_task")

    async def _send_daily_message_to_all_subscribers(
        self, content_getter, success_status: str
    ):
        """Helper function to send a daily message to all subscribers."""
        if not self.game.daily_q:
            print("No question available for today.")
            return

        content = content_getter()
        sent_to_ids = []

        for sub in self.game.get_subscribed_users():
            await self.send_message(
                content,
                is_channel=sub.is_channel,
                target_id=sub.id,
                success_status=success_status,
            )
            sent_to_ids.append(sub.id)

        self.logger.log_daily_question(
            question=self.game.daily_q, sent_to_users=sent_to_ids
        )

    def _log_task_error(self, e: Exception, task_name: str):
        """Logs an error for a background task."""
        print(f"An error occurred during the {task_name}: {e}")
        self.logger.log_messaging_event(
            direction="bot",
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
            self.logger.log_messaging_event(
                direction="to",
                method="Discord",
                recipient_or_sender=str(target_id),
                content=content,
                status=success_status,
            )
        except Exception as e:
            print(f"Error sending message to {target_id}: {e}")
            self.logger.log_messaging_event(
                direction="to",
                method="Discord",
                recipient_or_sender=str(target_id),
                content=content,
                status=f"failed - {e}",
            )


async def discord_bot_async(
    config: ConfigReader, questions: list[Question], logger: Logger
):
    """Main function to initialize and run the bot."""
    question_selector = QuestionSelector(questions, mode=config.get("QUESTION_MODE"))
    game = GameRunner(question_selector, logger, mode=config.get("GAME_MODE"))
    bot = DiscordBot(config.get("DISCORD_BOT_TOKEN"), game, config)
    await bot.run()


def run_discord_bot(config: ConfigReader, questions: list[Question], logger: Logger):
    try:
        asyncio.run(discord_bot_async(config, questions, logger))
    except KeyboardInterrupt:
        print("Bot shutdown requested by user.")
