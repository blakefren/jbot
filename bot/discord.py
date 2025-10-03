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
from log.logger import Logger
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

        # Sync commands.
        # TODO: commands don't appear in Discord for DMs to bot
        try:
            print("on_ready: syncing commands start")
            await self.tree.sync()
            print("on_ready: syncing commands finish")
        except Exception as e:
            print(e)

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


def set_bot_commands(bot: DiscordBot):

    @bot.hybrid_command(name="streak_breaker", aliases=["breakstreak", "break_streak"])
    async def streak_breaker(ctx: commands.Context, target_id: str):
        """Break another player's answer streak (POWERUP mode only)."""
        if bot.game.mode.name != "POWERUP":
            await bot.send_message(
                "Streak breaker is only available in POWERUP mode.", ctx=ctx
            )
            return
        players = bot.game.logger.get_guess_metrics(
            [], bot.game.question_selector.questions
        ).get("players", {})
        manager = PowerUpManager(players)
        result = manager.streak_breaker(str(ctx.author.id), target_id)
        await bot.send_message(result, ctx=ctx)

    @bot.hybrid_command(name="shield")
    async def shield(ctx: commands.Context):
        """Activate a shield to block the next attack (POWERUP mode only)."""
        if bot.game.mode.name != "POWERUP":
            await bot.send_message("Shield is only available in POWERUP mode.", ctx=ctx)
            return
        players = bot.game.logger.get_guess_metrics(
            [], bot.game.question_selector.questions
        ).get("players", {})
        manager = PowerUpManager(players)
        result = manager.use_shield(str(ctx.author.id))
        await bot.send_message(result, ctx=ctx)

    @bot.hybrid_command(name="bet")
    async def bet(ctx: commands.Context, amount: int):
        """Bet points for the current question (POWERUP mode only)."""
        if bot.game.mode.name != "POWERUP":
            await bot.send_message(
                "Betting is only available in POWERUP mode.", ctx=ctx
            )
            return
        players = bot.game.logger.get_guess_metrics(
            [], bot.game.question_selector.questions
        ).get("players", {})
        manager = PowerUpManager(players)
        result = manager.bet_points(str(ctx.author.id), amount)
        await bot.send_message(result, ctx=ctx)

    @bot.hybrid_command(name="shutdown", aliases=["quit", "exit"])
    async def shutdown(ctx: commands.Context):
        """Shuts down the bot."""
        if not await bot.is_owner(ctx.author):
            response_content = "You do not have permission to shut down the bot."
            await bot.send_message(
                response_content, ctx=ctx, success_status="unauthorized"
            )
            return

        print("Shutting down...")
        try:
            await bot.send_message("Shutting down...", ctx=ctx)
        except Exception as e:
            print(f"Failed to send shutdown message: {e}")
            bot.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender=str(ctx.author.id),
                content=f"Failed to send shutdown message: {e}",
                status="message_send_failed",
            )

        # Stop the tasks gracefully
        if bot.morning_message_task.is_running():
            bot.morning_message_task.stop()
            print("Morning task stopped.")
        if bot.reminder_message_task.is_running():
            bot.reminder_message_task.stop()
            print("Reminder task stopped.")
        if bot.evening_message_task.is_running():
            bot.evening_message_task.stop()
            print("Evening task stopped.")

        await asyncio.sleep(0.1)

        if hasattr(bot.http, "session") and not bot.http.session.closed:
            try:
                await bot.http.session.close()
                print("aiohttp session closed.")
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"Error closing aiohttp session: {e}")
                bot.logger.log_messaging_event(
                    direction="bot",
                    method="Discord",
                    recipient_or_sender="N/A",
                    content=f"Error closing aiohttp session during shutdown: {e}",
                    status="aiohttp_close_failed",
                )

        # TODO: should we close the logger here?
        try:
            await bot.close()
            print("Bot closed successfully.")
            bot.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender=str(ctx.author.id),
                content="Bot gracefully shut down.",
                status="completed",
            )
        except Exception as e:
            print(f"Error during bot.close(): {e}")
            bot.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender=str(ctx.author.id),
                content=f"Error during bot.close(): {e}",
                status="bot_close_failed",
            )

    @bot.hybrid_command(name="restart", aliases=["reboot", "r", "reset"])
    async def restart(ctx: commands.Context):
        """Restarts the bot."""
        if not await bot.is_owner(ctx.author):
            response_content = "You do not have permission to restart the bot."
            await bot.send_message(
                response_content, ctx=ctx, success_status="unauthorized"
            )
            return

        print("Restarting bot...")
        try:
            # Create restart info file to be read on next startup
            with open("restart.inf", "w") as f:
                f.write(f"{ctx.channel.id},{ctx.author.id}")
            await bot.send_message("Restarting bot...", ctx=ctx)

            # Cleanly close the bot before restarting
            await bot.close()

            # Replace the current process with a new one
            os.execv(sys.executable, ["python"] + sys.argv)

        except Exception as e:
            print(f"Failed to restart bot: {e}")
            bot.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender=str(ctx.author.id),
                content=f"Failed to restart bot: {e}",
                status="restart_failed",
            )
            # Clean up if something went wrong before restart
            if os.path.exists("restart.inf"):
                os.remove("restart.inf")

    @bot.hybrid_command(name="ping")
    async def ping(ctx: commands.Context):
        """Responds with 'Pong!' to test bot latency."""
        response_content = "Pong!"
        await bot.send_message(response_content, ctx=ctx)

    @bot.hybrid_command(name="question", aliases=["q", "query"])
    async def question(ctx: commands.Context):
        """Get a random question and answer."""
        random_q = bot.game.question_selector.get_random_question()
        if not random_q:
            await bot.send_message("Could not find a question.", ctx=ctx)
            return

        # TODO: is_channel is set to False during testing, when the bot is only
        # messaging a user. Make this settable at runtime.
        question_part = bot.game.format_question(random_q)
        answer_part = bot.game.format_answer(random_q)
        full_message = f"{question_part}\n{answer_part}"
        await bot.send_message(full_message, ctx=ctx)

    @bot.hybrid_command(name="when", aliases=["next", "howlong"])
    async def when(ctx: commands.Context):
        """Get the next event time. Shows the active question, if there is one."""
        morning_time_next = bot.morning_message_task.next_iteration
        evening_time_next = bot.evening_message_task.next_iteration
        next_datetime = min(morning_time_next, evening_time_next)
        response_content = ""

        # Next event is morning question.
        if morning_time_next < evening_time_next:
            response_content = (
                f"The next question is scheduled for <t:{int(next_datetime.timestamp())}>.\n"
                f"The next challenge is <t:{int(next_datetime.timestamp())}:R>."
            )
        # Next event is evening answer.
        else:
            response_content += f"The answer will be revealed at {evening_time_next.strftime('%I:%M %p %Z')}."
        await bot.send_message(response_content, ctx=ctx)

        # Remind the daily question, if after the morning send time.
        if bot.game.daily_q:
            question_part = bot.game.format_question(bot.game.daily_q)
            await bot.send_message(question_part, ctx=ctx)

    @bot.hybrid_command(name="answer", aliases=["a", "ans"])
    async def answer(ctx: commands.Context, *, guess: str):
        """Submits an answer for the current daily question."""
        if not bot.game.daily_q:
            # For test context, use ctx, not interaction
            await bot.send_message(
                "There is no active question right now.",
                ctx=ctx
            )
            return

        player_id = ctx.author.id
        player_name = ctx.author.display_name
        is_correct = bot.game.handle_guess(player_id, player_name, guess)

        # Log the guess submission event
        status = "correct_guess" if is_correct else "incorrect_guess"
        bot.logger.log_messaging_event(
            direction="from",
            method="Discord",
            recipient_or_sender=str(player_id),
            content=f"Answer: '{guess}'",
            status=status,
        )

        # Send a confirmation message
        if is_correct:
            response_content = "That is correct! Nicely done."
        else:
            response_content = "Sorry, that is not the correct answer."
        await bot.send_message(
            response_content, ctx=ctx
        )

    @bot.hybrid_command(name="subscribe", aliases=["sub"])
    async def subscribe(ctx: commands.Context):
        """Subscribes the context to daily question notifications."""
        subscriber = Subscriber.from_ctx(ctx)
        if subscriber in bot.game.get_subscribed_users():
            response_content = (
                f"Participant {subscriber.display_name}, you are already registered."
            )
            await bot.send_message(
                response_content, ctx=ctx, success_status="already_subscribed"
            )
        else:
            bot.game.add_subscriber(subscriber)
            response_content = (
                f"Participant {subscriber.display_name}, you are now registered for the daily games.\n"
                f"{len(bot.game.get_subscribed_users())} players are now in play."
            )
            await bot.send_message(
                response_content, ctx=ctx, success_status="subscribed"
            )

    @bot.hybrid_command(name="unsubscribe", aliases=["unsub"])
    async def unsubscribe(ctx: commands.Context):
        """Unsubscribes the context from daily question notifications."""
        subscriber = Subscriber.from_ctx(ctx)
        if subscriber in bot.game.get_subscribed_users():
            bot.game.remove_subscriber(subscriber)
            response_content = (
                f"Participant {subscriber.display_name}, you have been removed from the games.\n"
                f"There are {len(bot.game.get_subscribed_users())} players remaining."
            )
            await bot.send_message(
                response_content, ctx=ctx, success_status="unsubscribed"
            )
        else:
            response_content = (
                f"Participant {subscriber.display_name}, you were not registered for the games.\n"
                f"There are still {len(bot.game.get_subscribed_users())} players in play."
            )
            await bot.send_message(
                response_content, ctx=ctx, success_status="not_subscribed"
            )

    @bot.hybrid_command(name="history", aliases=["h", "metrics"])
    async def history(ctx: commands.Context):
        """Shows your personal game history and stats."""
        player_id = ctx.author.id
        player_name = ctx.author.display_name
        history_text = bot.game.get_player_history(player_id, player_name)
        await bot.send_message(history_text, ctx=ctx)

    @bot.hybrid_command(name="scores", aliases=["leaderboard", "s", "score"])
    async def scores(ctx: commands.Context):
        """Displays the current score leaderboard."""
        leaderboard = bot.game.get_scores_leaderboard()
        await bot.send_message(leaderboard, ctx=ctx)


async def discord_bot_async(
    config: ConfigReader, questions: list[Question], logger: Logger
):
    """Main function to initialize and run the bot."""
    question_selector = QuestionSelector(questions, mode=config.get("QUESTION_MODE"))
    game = GameRunner(question_selector, logger, mode=config.get("GAME_MODE"))
    bot = DiscordBot(config.get("DISCORD_BOT_TOKEN"), game, config)
    set_bot_commands(bot)
    await bot.run()


def run_discord_bot(config: ConfigReader, questions: list[Question], logger: Logger):
    try:
        asyncio.run(discord_bot_async(config, questions, logger))
    except KeyboardInterrupt:
        print("Bot shutdown requested by user.")
