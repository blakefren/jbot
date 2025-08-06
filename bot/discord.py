import asyncio
import datetime
import discord
import os
import re
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

    def __init__(self, bot_token: str, game: GameRunner, command_prefix: str = "!"):
        # discord.py specific setup
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guild_messages = True
        intents.dm_messages = True
        super().__init__(command_prefix=command_prefix, intents=intents)

        self.game = game
        self.logger = Logger()
        self.bot_token = bot_token
        self.ready_event_fired = False
        self.daily_q = None

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
        if MORNING_TIME < now.time() < EVENING_TIME and self.daily_q is None:
            print("Bot started after morning message time. Setting daily question.")
            self.daily_q = self.game.question_selector.get_question_for_today()
            if not self.daily_q:
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
        await self.send_morning_message()

    @tasks.loop(time=REMINDER_TIME)
    async def reminder_message_task(self):
        await self.send_reminder_message()

    @tasks.loop(time=EVENING_TIME)
    async def evening_message_task(self):
        await self.send_evening_message()

    async def send_message(
        self,
        content: str,
        is_channel: bool = False,
        target_id: int = -1,
        ctx=None,
        success_status="sent",
    ):
        """Sends a message to a Discord user, channel, or context."""
        assert (
            target_id >= 0 or ctx is not None
        ), "Either target_id or ctx must be provided."
        try:
            if ctx is not None:
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

    async def send_morning_message(self):
        """Sends the morning message and question to all subscribers."""
        print(f"Morning message task running at {datetime.datetime.now(TIMEZONE)}...")
        try:
            self.daily_q = self.game.question_selector.get_question_for_today()
            if not self.daily_q:
                print("No question found for today.")
                return
            sent_to_ids = []

            for sub in self.game.get_subscribed_users():
                flavor_message = (
                    "Good morning players!\n"
                    f"You have until {self.evening_message_task.next_iteration} to answer today's trivia question:"
                )
                question_part = self.format_question(self.daily_q)
                full_message = f"{flavor_message}\n{question_part}"
                await self.send_message(
                    full_message, target_id=sub.id, is_channel=sub.is_channel
                )
                sent_to_ids.append(str(sub.id))

            self.logger.log_daily_question(
                question=self.daily_q, sent_to_users=sent_to_ids
            )
        except Exception as e:
            print(f"An error occurred during the morning message task: {e}")
            self.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender="N/A",
                content=f"Error in morning message task: {e}",
                status="failed",
            )

    async def send_reminder_message(self):
        """Sends a reminder to all subscribers."""
        print(f"Reminder message task running at {datetime.datetime.now(TIMEZONE)}...")
        try:
            if not self.daily_q:
                print("No question found for today.")
                return
            sent_to_ids = []

            for sub in self.game.get_subscribed_users():
                response_content = (
                    "Reminder: your answers are due shortly. Today's question:"
                )
                question_part = self.format_question(self.daily_q)
                full_message = f"{response_content}\n{question_part}"
                await self.send_message(
                    full_message, target_id=sub.id, is_channel=sub.is_channel
                )
                sent_to_ids.append(str(sub.id))

            self.logger.log_daily_question(
                question=self.daily_q, sent_to_users=sent_to_ids
            )
        except Exception as e:
            print(f"An error occurred during the reminder message task: {e}")
            self.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender="N/A",
                content=f"Error in reminder message task: {e}",
                status="failed",
            )

    async def send_evening_message(self):
        """Sends the evening answer to all subscribers."""
        print(f"Evening message task running at {datetime.datetime.now(TIMEZONE)}...")
        try:
            if not self.daily_q:
                print("No question found for today.")
                return
            sent_to_ids = []

            for sub in self.game.get_subscribed_users():
                flavor_message = (
                    "Good evening players!\n"
                    f"Here is the answer to today's trivia question:"
                )
                question_part = self.format_question(self.daily_q)
                answer_part = self.format_answer(self.daily_q)
                full_message = f"{flavor_message}\n{question_part}\n{answer_part}"

                await self.send_message(
                    full_message, target_id=sub.id, is_channel=sub.is_channel
                )
                sent_to_ids.append(str(sub.id))

            self.logger.log_daily_question(
                question=self.daily_q, sent_to_users=sent_to_ids
            )
        except Exception as e:
            print(f"An error occurred during the evening message task: {e}")
            self.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender="N/A",
                content=f"Error in evening message task: {e}",
                status="failed",
            )

    def format_question(self, question: Question) -> str:
        """Internal helper method to format a trivia question."""
        return (
            f"**--- Question! ---**\n"
            f"Category: **{question.category}**\n"
            f"Value: **${question.clue_value}**\n"
            f"Question: **{question.question}**\n"
        )

    def format_answer(self, question: Question) -> str:
        """Internal helper method to format a trivia answer."""
        min_display_size = 15
        pad_size = max(min_display_size - len(question.answer), 0) // 2
        padded_answer = question.answer.center(len(question.answer) + pad_size * 2, " ")
        return f"Answer: ||**{padded_answer}**||\n"


def set_bot_commands(bot: DiscordBot):
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
            response_content = (
                "No questions available. Please check the question source."
            )
            await bot.send_message(
                response_content, ctx=ctx, success_status="no_questions"
            )
            return

        # TODO: is_channel is set to False during testing, when the bot is only
        # messaging a user. Make this settable at runtime.
        question_part = bot.format_question(random_q)
        answer_part = bot.format_answer(random_q)
        full_message = f"{question_part}\n{answer_part}"
        await bot.send_message(full_message, ctx=ctx)

    @bot.hybrid_command(name="when", aliases=["next", "howlong"])
    async def when(ctx: commands.Context):
        """Get the next event time. Shows the active question, if there is one."""
        morning_time_next = bot.morning_message_task.next_iteration
        evening_time_next = bot.evening_message_task.next_iteration
        next_datetime = min(morning_time_next, evening_time_next)
        time_until = next_datetime - datetime.datetime.now(TIMEZONE)
        response_content = ""

        # Next event is morning question.
        if morning_time_next < evening_time_next:
            response_content = (
                f"The next question is scheduled for {next_datetime.strftime('%Y-%m-%d %H:%M:%S %Z')}.\n"
                f"You have {time_until} until the next challenge."
            )
        # Next event is evening answer.
        else:
            response_content = (
                f"Today's answer is scheduled for {next_datetime.strftime('%Y-%m-%d %H:%M:%S %Z')}.\n"
                f"You have {time_until} remaining to play."
            )
        await bot.send_message(response_content, ctx=ctx)

        # Remind the daily question, if after the morning send time.
        if bot.daily_q:
            reminder_message = "Resending today's question:"
            question_part = bot.format_question(bot.daily_q)
            full_message = f"{reminder_message}\n{question_part}"
            await bot.send_message(full_message, ctx=ctx)

    @bot.hybrid_command(name="answer", aliases=["a", "ans"])
    async def answer(ctx: commands.Context, *, guess: str, skip_confirmation=False):
        """Submits an answer for the current daily question."""
        if not bot.daily_q:
            await bot.send_message(
                "There is no active question to answer right now.", ctx=ctx
            )
            return

        # Check the answer
        g = guess.strip().lower()
        a = bot.daily_q.answer.strip().lower()
        is_correct = re.search(g, a) is not None
        bot.logger.log_player_guess(
            ctx.author.id, ctx.author.name, bot.daily_q.id, g, is_correct
        )

        # Confirm the answer, if enabled.
        if skip_confirmation:
            return
        status = "correct_guess" if is_correct else "incorrect_guess"
        bot.logger.log_messaging_event(
            direction="from",
            method="Discord",
            recipient_or_sender=str(ctx.author.id),
            content=f"Answer: '{guess}'",
            status=status,
        )
        if is_correct:
            response_content = f"That is correct, {ctx.author.display_name}! Well done."
        else:
            response_content = f"Sorry, '{guess}' is not the correct answer."

        answer_part = bot.format_answer(bot.daily_q)
        full_message = f"{response_content}\n{answer_part}"
        await bot.send_message(full_message, ctx=ctx)

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
        """Get player guess history."""
        history = bot.logger.read_guess_history(user_id=ctx.author.id)
        metrics = bot.logger.get_guess_metrics(
            history, bot.game.question_selector.questions
        )

        full_message = ""
        player_metrics = metrics["players"].get(str(ctx.author.id), None)
        if player_metrics:
            correct_rate = player_metrics.get("correct_rate", 0)
            player_part = (
                f"--{ctx.author.display_name}'s data--\n"
                f"Player guesses:  {player_metrics.get('total_guesses')}\n"
                f"Correct guesses: {player_metrics.get('correct_guesses')}\n"
                f"Correct rate:    {correct_rate:.2f}\n"
                f"Total score:     {player_metrics.get('score')}"
            )
            full_message += player_part

        global_correct_rate = metrics.get("global_correct_rate", 0)
        global_part = (
            f"\n\n--Global data--\n"
            f"Global guesses:   {metrics.get('total_guesses')}\n"
            f"Unique questions: {metrics.get('unique_questions')}\n"
            f"Correct rate:     {global_correct_rate:.2f}\n"
            f"Global score:     {metrics.get('global_score')}"
        )
        full_message += global_part

        await bot.send_message(full_message, ctx=ctx, success_status="history")

    @bot.hybrid_command(name="scores", aliases=["leaderboard", "s", "score"])
    async def scores(ctx: commands.Context):
        """Get all player scores."""
        history = bot.logger.read_guess_history()
        metrics = bot.logger.get_guess_metrics(
            history, bot.game.question_selector.questions
        )
        players_data = metrics.get("players", {})

        if not players_data:
            await bot.send_message("No player scores found.", ctx=ctx)
            return

        # Sort players by score
        sorted_players = sorted(
            players_data.items(), key=lambda item: item[1].get("score", 0), reverse=True
        )

        if not sorted_players:
            await bot.send_message("No player scores found.", ctx=ctx)
            return

        response_content = "-- Player Scores --\n"
        for i, (user_id, data) in enumerate(sorted_players, 1):
            try:
                user = await bot.fetch_user(int(user_id))
                display_name = user.display_name
            except discord.NotFound:
                display_name = f"Unknown User (ID: {user_id})"
            except Exception as e:
                display_name = f"Unknown User (ID: {user_id})"
                print(f"Could not fetch user {user_id}: {e}")

            score = data.get("score", 0)
            response_content += f"{i}. {display_name}: {score}\n"

        await bot.send_message(response_content, ctx=ctx, success_status="scores")


async def discord_bot_async(config: ConfigReader, questions: list[Question]):
    """Main function to initialize and run the bot."""
    question_selector = QuestionSelector(questions, mode=config.get("QUESTION_MODE"))
    game = GameRunner(question_selector, mode=config.get("GAME_MODE"))
    bot = DiscordBot(config.get("DISCORD_BOT_TOKEN"), game)
    set_bot_commands(bot)
    await bot.run()


def run_discord_bot(config: ConfigReader, questions: list[Question]):
    try:
        asyncio.run(discord_bot_async(config, questions))
    except KeyboardInterrupt:
        print("Bot shutdown requested by user.")
