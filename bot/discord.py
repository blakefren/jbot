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

TIMEZONE = ZoneInfo("US/Pacific")
MORNING_TIME = datetime.time(hour=8, minute=0, tzinfo=TIMEZONE)
EVENING_TIME = datetime.time(hour=20, minute=0, tzinfo=TIMEZONE)


class Subscriber:
    """
    Represents a subscriber to the Jeopardy! bot, which can be a user or a channel.
    """

    def __init__(self, ctx):
        self.id = ctx.channel.id if ctx.guild else ctx.author.id
        self.display_name = ctx.author.display_name
        self.is_channel = ctx.guild is not None
        # Store the actual context object for direct sending if needed,
        # but for scheduled tasks, ID and is_channel are usually sufficient.
        self.ctx = ctx

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return isinstance(other, Subscriber) and self.id == other.id


class DiscordBot(commands.Bot):
    """
    A Python library for sending and receiving Discord messages for a Jeopardy! bot.
    """

    def __init__(
        self, bot_token=None, command_prefix="!", questions: list[Question] = None
    ):
        """
        Initializes the DiscordBot with a Discord bot token and command prefix.

        Args:
            bot_token (str, optional): Your Discord Bot Token.
            command_prefix (str): The prefix for bot commands (e.g., !question).
            questions (list[Question]): A list of JeopardyQuestion objects.
        """
        self.bot_token = bot_token
        if not self.bot_token:
            raise ValueError("Discord Bot Token must be provided.")

        # Define intents. Intents specify which events your bot wants to receive from Discord.
        # MESSAGE_CONTENT is required to read message content from users (since Discord API v8).
        # GUILD_MESSAGES is for messages in guilds (servers).
        # DIRECT_MESSAGES is for direct messages to the bot.
        intents = discord.Intents.default()
        intents.message_content = True  # Required to read message content
        intents.guild_messages = True  # For messages in server channels
        intents.dm_messages = True  # For direct messages to the bot

        # Initialize the commands.Bot superclass
        super().__init__(command_prefix=command_prefix, intents=intents)

        self.ready_event_fired = False  # Flag to ensure on_ready logic runs once
        self.subscribed_contexts = set()  # Set to track subscribed contexts
        self.questions = questions
        assert self.questions, "Questions must be provided to the DiscordBot."
        self.logger = Logger()  # Initialize the logger here

        print("DiscordBot initialized successfully.")

    def get_next_question_time(self):
        """
        Returns the next scheduled time for the daily question.

        Returns:
            datetime.datetime: The next time the daily question should be sent.
        """
        return min(
            self.morning_message.next_iteration, self.evening_message.next_iteration
        )

    def get_morning_message_flavor(self):
        """
        Returns a string representing the morning message flavor.
        This can be customized based on your bot's theme or personality.
        """
        prompts = [
            "`Attention, players. Today's game begins now. Good luck.`",
            "`Wake up, players. The dawn has broken, and with it, a new challenge. Do not disappoint us.`",
            "`The morning bell has rung. It's time to play.`",
        ]
        index = randint(0, len(prompts) - 1)
        return prompts[index]

    def get_evening_message_flavor(self):
        """
        Returns a string representing the morning message flavor.
        This can be customized based on your bot's theme or personality.
        """
        prompts = [
            "`The day's trials are complete. You have survived another round. Rest, for tomorrow brings new games.`",
            "`All contests are concluded for the day. Return to your designated quarters. Further instructions await the morning.`",
            "`Night falls. The games cease. Sleep well, or don't.`",
        ]
        index = randint(0, len(prompts) - 1)
        return prompts[index]

    async def setup_hook(self):
        # This is called after login but before connecting to Discord
        print("Setup hook called!")
        # It's generally better to start tasks in on_ready, as the bot is fully ready there.
        # If you need tasks to run immediately after setup, this is the place.
        # For now, keeping task starting in on_ready for full bot readiness.
        pass

    async def on_ready(self):
        """
        Event handler that runs when the bot successfully connects to Discord.
        This is where scheduled tasks should be started.
        """
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
            self.ready_event_fired = True  # Set flag to prevent re-execution

            # Start the scheduled tasks
            if not self.morning_message.is_running():
                self.morning_message.start()
                print("Morning message task started.")
            if not self.evening_message.is_running():
                self.evening_message.start()
                print("Evening message task started.")
        else:
            print("Bot reconnected.")
            self.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender=str(self.user.id),
                content="Bot reconnected.",
                status="success",
            )

    async def on_message(self, message):
        """
        Event handler that runs whenever a message is sent in a channel the bot can see.
        This is where you'd process incoming user messages.

        Args:
            message (discord.Message): The message object.
        """
        # Ignore messages from the bot itself to prevent infinite loops
        if message.author == self.user:
            return

        print(
            f"Received message from {message.author} in {'DM' if message.guild is None else message.guild.name}: {message.content}"
        )
        self.logger.log_messaging_event(
            direction="from",
            method="Discord",
            recipient_or_sender=str(message.author.id),
            content=message.content,
            status="received",
        )

        # Process commands (if any)
        await self.process_commands(message)

        # Example: Respond to a specific message
        if "hello bot" in message.content.lower():
            response_content = (
                f"`Greetings, contestant. Your presence has been registered.`"
            )
            await message.channel.send(response_content)
            self.logger.log_messaging_event(
                direction="to",
                method="Discord",
                recipient_or_sender=str(message.channel.id),
                content=response_content,
                status="sent",
            )

    async def send_message_to_channel(self, channel_id, message_body):
        """
        Sends a message to a specific Discord channel.

        Args:
            channel_id (int): The ID of the Discord channel.
            message_body (str): The content of the message.
        """
        try:
            channel = self.get_channel(channel_id)
            if channel:
                await channel.send(message_body)
                print(f"Message sent successfully to channel ID {channel_id}.")
                self.logger.log_messaging_event(
                    direction="to",
                    method="Discord",
                    recipient_or_sender=str(channel_id),
                    content=message_body,
                    status="sent",
                )
            else:
                print(f"Error: Channel with ID {channel_id} not found or inaccessible.")
                self.logger.log_messaging_event(
                    direction="to",
                    method="Discord",
                    recipient_or_sender=str(channel_id),
                    content=message_body,
                    status="failed - channel not found",
                )
        except Exception as e:
            print(f"Error sending message to channel {channel_id}: {e}")
            self.logger.log_messaging_event(
                direction="to",
                method="Discord",
                recipient_or_sender=str(channel_id),
                content=message_body,
                status=f"failed - {e}",
            )

    async def send_message_to_user(self, user_id, message_body):
        """
        Sends a direct message to a specific Discord user.

        Args:
            user_id (int): The ID of the Discord user.
            message_body (str): The content of the message.
        """
        try:
            user = await self.fetch_user(user_id)
            if user:
                await user.send(message_body)
                print(f"Direct message sent successfully to user ID {user_id}.")
                self.logger.log_messaging_event(
                    direction="to",
                    method="Discord",
                    recipient_or_sender=str(user_id),
                    content=message_body,
                    status="sent",
                )
            else:
                print(f"Error: User with ID {user_id} not found.")
                self.logger.log_messaging_event(
                    direction="to",
                    method="Discord",
                    recipient_or_sender=str(user_id),
                    content=message_body,
                    status="failed - user not found",
                )
        except Exception as e:
            print(f"Error sending direct message to user {user_id}: {e}")
            self.logger.log_messaging_event(
                direction="to",
                method="Discord",
                recipient_or_sender=str(user_id),
                content=message_body,
                status=f"failed - {e}",
            )

    async def send_jeopardy_question(
        self, target_id=None, is_channel=None, ctx=None, question: Question = None
    ):
        """
        Sends a Jeopardy! question to a specified Discord channel or user.

        Args:
            target_id (int): The ID of the channel or user.
            is_channel (bool): True if target_id is a channel ID, False if a user ID.
            ctx (commands.Context, optional): The context object if sending via a command.
            question (Question): The Jeopardy! question object.
        """
        if question is None:
            print("Error: No question provided to send_jeopardy_question.")
            return

        # Ensure metadata exists and has 'air_date'
        air_date_info = question.metadata.get("air_date", "N/A")

        message_body = (
            f"**--- Jeopardy Question! ---**\n"
            f"Category: **{question.category}**\n"
            f"Value: **${question.clue_value}**\n"
            f"Air date: **{air_date_info}**\n"
            f"Question: **{question.question}**\n"
        )
        if ctx:
            await ctx.send(message_body)
            self.logger.log_messaging_event(
                direction="to",
                method="Discord",
                recipient_or_sender=str(ctx.channel.id),
                content=message_body,
                status="sent",
            )
            return

        print(
            f"Attempting to send Jeopardy question to {'channel' if is_channel else 'user'} ID {target_id}..."
        )
        if is_channel:
            await self.send_message_to_channel(target_id, message_body)
        else:
            await self.send_message_to_user(target_id, message_body)

    async def send_jeopardy_answer(
        self, target_id=None, is_channel=None, ctx=None, question: Question = None
    ):
        """
        Sends the answer to a Jeopardy! question to a specified Discord channel or user.
        The answer is hidden as a spoiler.

        Args:
            target_id (int): The ID of the channel or user.
            is_channel (bool): True if target_id is a channel ID, False if a user ID.
            ctx (commands.Context, optional): The context object if sending via a command.
            question (Question): The Jeopardy! question object.
        """
        if question is None:
            print("Error: No question provided to send_jeopardy_answer.")
            return

        message_body = f"Answer: ||**{question.answer}**||\n"

        if ctx:
            await ctx.send(message_body)
            self.logger.log_messaging_event(
                direction="to",
                method="Discord",
                recipient_or_sender=str(ctx.channel.id),
                content=message_body,
                status="sent",
            )
            return

        print(
            f"Attempting to send Jeopardy answer to {'channel' if is_channel else 'user'} ID {target_id}..."
        )
        if is_channel:
            await self.send_message_to_channel(target_id, message_body)
        else:
            await self.send_message_to_user(target_id, message_body)

    @tasks.loop(time=MORNING_TIME)
    async def morning_message(self):
        print(f"Evening message task running at {datetime.datetime.now()}...")
        if not self.questions:
            print("No questions loaded for morning message. Skipping.")
            return

        # Get a random question based on the current date.
        # Ensure 'questions' is accessible, e.g., via self.questions
        current_time = datetime.datetime.now(TIMEZONE)
        # Using ordinal for index is fine, but ensure it doesn't go out of bounds
        index = current_time.date().toordinal() % len(self.questions)
        daily_q = self.questions[index]

        for sub in self.subscribed_contexts:
            ctx = None
            if sub.is_channel:
                ctx = self.get_channel(sub.id)
            else:
                ctx = await self.fetch_user(sub.id)
            if ctx:
                flavor_message = self.get_morning_message_flavor()
                await ctx.send(flavor_message)
                self.logger.log_messaging_event(
                    direction="to",
                    method="Discord",
                    recipient_or_sender=str(sub.id),
                    content=flavor_message,
                    status="sent",
                )
            await self.send_jeopardy_question(
                target_id=sub.id, is_channel=sub.is_channel, question=daily_q
            )
            self.logger.log_daily_question(
                question=daily_q,
                sent_to_users=[str(sub.id)],
            )

    @tasks.loop(time=EVENING_TIME)
    async def evening_message(self):
        print(f"Evening message task running at {datetime.datetime.now()}...")
        if not self.questions:
            print("No questions loaded for evening message. Skipping.")
            return

        # Get a random question based on the current date.
        current_time = datetime.datetime.now(TIMEZONE)
        index = current_time.date().toordinal() % len(self.questions)
        daily_q = self.questions[index]

        for sub in self.subscribed_contexts:
            ctx = None
            if sub.is_channel:
                ctx = self.get_channel(sub.id)
            else:
                ctx = await self.fetch_user(sub.id)
            if ctx:
                flavor_message = self.get_evening_message_flavor()
                await ctx.send(flavor_message)
                self.logger.log_messaging_event(
                    direction="to",
                    method="Discord",
                    recipient_or_sender=str(sub.id),
                    content=flavor_message,
                    status="sent",
                )
            await self.send_jeopardy_question(
                target_id=sub.id, is_channel=sub.is_channel, question=daily_q
            )
            await self.send_jeopardy_answer(
                target_id=sub.id, is_channel=sub.is_channel, question=daily_q
            )


# Load configuration
async def run_discord_bot(config: ConfigReader, questions: list[Question]):
    # Initialize the bot, passing the questions list
    bot = DiscordBot(config.get("DISCORD_BOT_TOKEN"), questions=questions)

    @bot.command(name="shutdown", aliases=["quit", "exit"])
    async def shutdown(ctx):
        if await bot.is_owner(ctx.author):  # Ensure only the bot owner can shut down
            print("Shutting down...")
            await ctx.send("Shutting down...")
            await bot.close()
        else:
            response_content = "You do not have permission to shut down the bot."
            await ctx.send(response_content)
            bot.logger.log_messaging_event(
                direction="to",
                method="Discord",
                recipient_or_sender=str(ctx.channel.id),
                content=response_content,
                status="permission denied",
            )

    @bot.command(name="ping")
    async def ping(ctx):
        """Responds with 'Pong!' to test bot latency."""
        response_content = "Pong!"
        await ctx.send(response_content)
        bot.logger.log_messaging_event(
            direction="to",
            method="Discord",
            recipient_or_sender=str(ctx.channel.id),
            content=response_content,
            status="sent",
        )

    @bot.command(name="question", aliases=["q", "query"])
    async def question(ctx):
        bot.logger.log_messaging_event(
            direction="from",
            method="Discord",
            recipient_or_sender=str(ctx.author.id),
            content=ctx.message.content,
            status="command received",
        )
        random_q = get_random_question(bot.questions)
        await bot.send_jeopardy_question(ctx=ctx, question=random_q)
        await bot.send_jeopardy_answer(ctx=ctx, question=random_q)

    @bot.command(name="when", aliases=["next", "howlong"])
    async def when(ctx):
        next_datetime = bot.get_next_question_time()
        reponse_content = (
            f"Next question time: {next_datetime.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"Next question will be sent in {next_datetime - datetime.datetime.now(TIMEZONE)}."
        )
        await ctx.send(reponse_content)
        bot.logger.log_messaging_event(
            direction="to",
            method="Discord",
            recipient_or_sender=str(ctx.channel.id),
            content=response_content,
            status="sent",
        )

    @bot.command(name="subscribe", aliases=["sub"])
    async def subscribe(ctx):
        """Subscribes the context to daily question notifications."""
        subscriber = Subscriber(ctx)
        bot.subscribed_contexts.add(subscriber)
        response_content = (
            f"You have subscribed to daily questions, {subscriber.display_name}!\n"
            f"There are {len(bot.subscribed_contexts)} players subscribed."
        )
        await ctx.send(response_content)
        bot.logger.log_messaging_event(
            direction="to",
            method="Discord",
            recipient_or_sender=str(ctx.channel.id),
            content=response_content,
            status="subscribed",
        )

        bot.logger.log_messaging_event(
            direction="bot",
            method="Discord",
            recipient_or_sender=str(subscriber.id),
            content=f"User/Channel {subscriber.display_name} subscribed.",
            status="user_action",
        )

    @bot.command(name="unsubscribe", aliases=["unsub"])
    async def unsubscribe(ctx):
        """Unsubscribes the context to daily question notifications."""
        subscriber = Subscriber(ctx)
        if subscriber in bot.subscribed_contexts:
            bot.subscribed_contexts.remove(subscriber)
            response_content = (
                f"You have unsubscribed from daily questions, {subscriber.display_name}!\n"
                f"There are {len(bot.subscribed_contexts)} players remaining."
            )
            await ctx.send(response_content)
            bot.logger.log_messaging_event(
                direction="to",
                method="Discord",
                recipient_or_sender=str(ctx.channel.id),
                content=response_content,
                status="unsubscribed",
            )
            bot.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender=str(subscriber.id),
                content=f"User/Channel {subscriber.display_name} unsubscribed.",
                status="user_action",
            )
        else:
            response_content = (
                f"You were not subscribed, {subscriber.display_name}.\n"
                f"There are still {len(bot.subscribed_contexts)} players subscribed."
            )
            await ctx.send(response_content)
            bot.logger.log_messaging_event(
                direction="to",
                method="Discord",
                recipient_or_sender=str(ctx.channel.id),
                content=response_content,
                status="not subscribed",
            )

    # Start the bot
    # The tasks will be started within the on_ready event
    await bot.start(bot.bot_token)


def test_discord_bot(config: ConfigReader, questions: list[Question]):
    # Run the asynchronous function
    asyncio.run(run_discord_bot(config, questions))
