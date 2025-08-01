import asyncio
import discord
import datetime

from random import randint
from zoneinfo import ZoneInfo
from readers.question import Question  # Assuming this is your JeopardyQuestion class
from readers.tsv import get_random_question  # Assuming this function exists
from cfg.main import ConfigReader
from discord.ext import commands, tasks
from log.logger import Logger
from readers.question_selector import QuestionSelector

# TODO: read timezone from config
TIMEZONE = ZoneInfo("US/Pacific")
MORNING_TIME = datetime.time(hour=8, minute=0, tzinfo=TIMEZONE)
EVENING_TIME = datetime.time(hour=20, minute=0, tzinfo=TIMEZONE)

class DiscordBot(commands.Bot, MessagingBot):
    """
    A concrete Discord bot implementation that extends MessagingBot.
    Handles Discord-specific functionality like commands and tasks.
    """
    def __init__(self, bot_token: str, game: GameType, logger: Logger, command_prefix: str = "!"):
        # discord.py specific setup
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guild_messages = True
        intents.dm_messages = True
        super().__init__(command_prefix=command_prefix, intents=intents)

        # MessagingBot-specific properties
        self.game = game
        self.logger = logger
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
        if not self.ready_event_fired:
            print(f"Logged in as {self.user} (ID: {self.user.id})")
            self.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender=str(self.user.id),
                content=f"Bot logged in as {self.user.name}",
                status="success"
            )
            print("------")
            self.ready_event_fired = True
            
            # Start the tasks
            if not self.morning_message_task.is_running():
                self.morning_message_task.start()
                print("Morning message task started.")
            if not self.evening_message_task.is_running():
                self.evening_message_task.start()
                print("Evening message task started.")
        else:
            print("Bot reconnected.")
            self.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender=str(self.user.id),
                content="Bot reconnected.",
                status="success"
            )

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
            status="received"
        )
        await self.process_commands(message)

    @tasks.loop(time=MORNING_TIME)
    async def morning_message_task(self):
        await self.send_morning_message()

    @tasks.loop(time=EVENING_TIME)
    async def evening_message_task(self):
        await self.send_evening_message()

    async def send_message(self, recipient_id: int, content: str, is_channel: bool):
        """Sends a message to a Discord user or channel."""
        try:
            if is_channel:
                channel = self.get_channel(recipient_id)
                if channel:
                    await channel.send(content)
            else:
                user = await self.fetch_user(recipient_id)
                if user:
                    await user.send(content)
            self.logger.log_messaging_event(
                direction="to",
                method="Discord",
                recipient_or_sender=str(recipient_id),
                content=content,
                status="sent"
            )
        except Exception as e:
            print(f"Error sending message to {recipient_id}: {e}")
            self.logger.log_messaging_event(
                direction="to",
                method="Discord",
                recipient_or_sender=str(recipient_id),
                content=content,
                status=f"failed - {e}"
            )

    async def send_morning_message(self):
        """Sends the morning message and question to all subscribers."""
        print(f"Morning message task running at {datetime.datetime.now(TIMEZONE)}...")
        try:
            daily_q = self.game.question_selector.get_question_for_today()
            if not daily_q:
                print("No question found for today.")
                return

            sent_to_ids = []
            flavor_message = "Attention, players. Today's game begins now. Good luck."
            for sub in self.game.get_subscribed_users():
                await self.send_message(sub.id, flavor_message, sub.is_channel)
                await self._send_jeopardy_question(sub.id, sub.is_channel, daily_q)
                sent_to_ids.append(str(sub.id))
            
            self.logger.log_daily_question(question=daily_q, sent_to_users=sent_to_ids)
        except Exception as e:
            print(f"An error occurred during the morning message task: {e}")
            self.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender="N/A",
                content=f"Error in morning message task: {e}",
                status="failed"
            )

    async def send_evening_message(self):
        """Sends the evening answer to all subscribers."""
        print(f"Evening message task running at {datetime.datetime.now(TIMEZONE)}...")
        try:
            daily_q = self.game.question_selector.get_question_for_today()
            if not daily_q:
                print("No question found for today.")
                return
                
            sent_to_ids = []
            flavor_message = "The day's trials are complete. You have survived another round. Rest, for tomorrow brings new games."
            for sub in self.game.get_subscribed_users():
                await self.send_message(sub.id, flavor_message, sub.is_channel)
                await self._send_jeopardy_answer(sub.id, sub.is_channel, daily_q)
                sent_to_ids.append(str(sub.id))
            
            self.logger.log_daily_question(question=daily_q, sent_to_users=sent_to_ids)
        except Exception as e:
            print(f"An error occurred during the evening message task: {e}")
            self.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender="N/A",
                content=f"Error in evening message task: {e}",
                status="failed"
            )

    async def _send_jeopardy_question(self, target_id: int, is_channel: bool, question: Question):
        """Internal helper method to format and send a Jeopardy question."""
        air_date_info = question.metadata.get("air_date", "N/A")
        message_body = (
            f"**--- Jeopardy Question! ---**\n"
            f"Category: **{question.category}**\n"
            f"Value: **${question.clue_value}**\n"
            f"Air date: **{air_date_info}**\n"
            f"Question: **{question.question}**\n"
        )
        await self.send_message(target_id, message_body, is_channel)

    async def _send_jeopardy_answer(self, target_id: int, is_channel: bool, question: Question):
        """Internal helper method to format and send a Jeopardy answer."""
        message_body = f"Answer: ||**{question.answer}**||\n"
        await self.send_message(target_id, message_body, is_channel)

    @commands.command(name="shutdown", aliases=["quit", "exit"])
    async def shutdown(self, ctx: commands.Context):
        if await self.is_owner(ctx.author):
            print("Shutting down...")
            self.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender=str(ctx.author.id),
                content="Bot shutdown initiated by owner.",
                status="initiated"
            )

            try:
                await ctx.send("Shutting down...")
            except Exception as e:
                print(f"Failed to send shutdown message: {e}")
                self.logger.log_messaging_event(
                    direction="bot",
                    method="Discord",
                    recipient_or_sender=str(ctx.author.id),
                    content=f"Failed to send shutdown message: {e}",
                    status="message_send_failed"
                )

            # Stop the tasks gracefully
            if self.morning_message_task.is_running():
                self.morning_message_task.stop()
                print("Morning task stopped.")
            if self.evening_message_task.is_running():
                self.evening_message_task.stop()
                print("Evening task stopped.")
            
            await asyncio.sleep(0.1)

            if hasattr(self.http, 'session') and not self.http.session.closed:
                try:
                    await self.http.session.close()
                    print("aiohttp session closed.")
                    await asyncio.sleep(0.1)
                except Exception as e:
                    print(f"Error closing aiohttp session: {e}")
                    self.logger.log_messaging_event(
                        direction="bot",
                        method="Discord",
                        recipient_or_sender="N/A",
                        content=f"Error closing aiohttp session during shutdown: {e}",
                        status="aiohttp_close_failed"
                    )

            try:
                await self.close()
                print("Bot closed successfully.")
                self.logger.log_messaging_event(
                    direction="bot",
                    method="Discord",
                    recipient_or_sender=str(ctx.author.id),
                    content="Bot gracefully shut down.",
                    status="completed"
                )
            except Exception as e:
                print(f"Error during bot.close(): {e}")
                self.logger.log_messaging_event(
                    direction="bot",
                    method="Discord",
                    recipient_or_sender=str(ctx.author.id),
                    content=f"Error during bot.close(): {e}",
                    status="bot_close_failed"
                )

        else:
            response_content = "You do not have permission to shut down the bot."
            await ctx.send(response_content)
            self.logger.log_messaging_event(
                direction="to",
                method="Discord",
                recipient_or_sender=str(ctx.channel.id),
                content=response_content,
                status="permission denied"
            )

    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context):
        """Responds with 'Pong!' to test bot latency."""
        response_content = "Pong!"
        await ctx.send(response_content)
        self.logger.log_messaging_event(
            direction="to",
            method="Discord",
            recipient_or_sender=str(ctx.channel.id),
            content=response_content,
            status="sent"
        )
    
    @commands.command(name="question", aliases=["q", "query"])
    async def question(self, ctx: commands.Context):
        random_q = self.game.question_selector.get_random_question()
        if not random_q:
            response_content = "No questions available. Please check the question source."
            await ctx.send(response_content)
            return

        await self._send_jeopardy_question(ctx.channel.id, True, random_q)
        await self._send_jeopardy_answer(ctx.channel.id, True, random_q)
        self.logger.log_daily_question(question=random_q, sent_to_users=[str(ctx.channel.id)])
    
    @commands.command(name="when", aliases=["next", "howlong"])
    async def when(self, ctx: commands.Context):
        """Tells the user when the next question is scheduled."""
        # Note: In this refactored design, `next_iteration` is on the task, not the bot.
        morning_task = self.morning_message_task
        evening_task = self.evening_message_task

        if not morning_task.is_running() or not evening_task.is_running():
            next_datetime = datetime.datetime.now(TIMEZONE) + timedelta(minutes=1) # Fallback
            response_content = "Daily question tasks are not running. Next question time is unknown."
        else:
            next_datetime = min(morning_task.next_iteration, evening_task.next_iteration)
            time_until = next_datetime - datetime.datetime.now(TIMEZONE)
            response_content = (
                f"The next game is scheduled for {next_datetime.strftime('%Y-%m-%d %H:%M:%S %Z')}.\n"
                f"You have {time_until} until the next challenge."
            )

        await ctx.send(response_content)
        self.logger.log_messaging_event(
            direction="to",
            method="Discord",
            recipient_or_sender=str(ctx.channel.id),
            content=response_content,
            status="sent"
        )

    @commands.command(name="subscribe", aliases=["sub"])
    async def subscribe(self, ctx: commands.Context):
        """Subscribes the context to daily question notifications."""
        subscriber = Subscriber(ctx)
        self.game.add_subscriber(subscriber)
        response_content = (
            f"Participant {subscriber.display_name}, you are now registered for the daily games.\n"
            f"{len(self.game.get_subscribed_users())} players are now in play."
        )
        await ctx.send(response_content)
        self.logger.log_messaging_event(
            direction="to",
            method="Discord",
            recipient_or_sender=str(ctx.channel.id),
            content=response_content,
            status="subscribed"
        )
        self.logger.log_messaging_event(
            direction="bot",
            method="Discord",
            recipient_or_sender=str(subscriber.id),
            content=f"User/Channel {subscriber.display_name} subscribed.",
            status="user_action"
        )

    @commands.command(name="unsubscribe", aliases=["unsub"])
    async def unsubscribe(self, ctx: commands.Context):
        """Unsubscribes the context from daily question notifications."""
        subscriber = Subscriber(ctx)
        if subscriber in self.game.get_subscribed_users():
            self.game.remove_subscriber(subscriber)
            response_content = (
                f"Participant {subscriber.display_name}, you have been removed from the games.\n"
                f"There are {len(self.game.get_subscribed_users())} players remaining."
            )
            await ctx.send(response_content)
            self.logger.log_messaging_event(
                direction="to",
                method="Discord",
                recipient_or_sender=str(ctx.channel.id),
                content=response_content,
                status="unsubscribed"
            )
            self.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender=str(subscriber.id),
                content=f"User/Channel {subscriber.display_name} unsubscribed.",
                status="user_action"
            )
        else:
            response_content = (
                f"Participant {subscriber.display_name}, you were not registered for the games.\n"
                f"There are still {len(self.game.get_subscribed_users())} players in play."
            )
            await ctx.send(response_content)
            self.logger.log_messaging_event(
                direction="to",
                method="Discord",
                recipient_or_sender=str(ctx.channel.id),
                content=response_content,
                status="not subscribed"
            )


async def run_discord_bot(config: ConfigReader, questions: list[Question]):
    """Main function to initialize and run the bot."""
    logger = Logger()
    question_selector = QuestionSelector(questions, mode="daily")
    game = GameType(question_selector)
    bot = DiscordBot(config.get("DISCORD_BOT_TOKEN"), game, logger)
    await bot.run()


def test_discord_bot(config: ConfigReader, questions: list[Question]):
    # Run the asynchronous function
    asyncio.run(run_discord_bot(config, questions))
