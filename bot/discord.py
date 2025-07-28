import time
import discord

from readers.tsv import get_random_question
from readers.main import ConfigReader
from discord.ext import commands

class DiscordBot(commands.Bot):
    """
    A Python library for sending and receiving Discord messages for a Jeopardy! bot.
    """

    def __init__(self, bot_token=None, command_prefix="!"):
        """
        Initializes the DiscordBot with a Discord bot token and command prefix.

        Args:
            bot_token (str, optional): Your Discord Bot Token.
            command_prefix (str): The prefix for bot commands (e.g., !question).
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
        print("DiscordBot initialized successfully.")

    async def setup_hook(self):
        # This is called after login but before connecting to Discord
        print("Setup hook called!")
        self.bg_task = self.loop.create_task(self.on_ready())

    async def on_ready(self):
        """
        Event handler that runs when the bot successfully connects to Discord.
        """
        if not self.ready_event_fired:
            print(f"Logged in as {self.user} (ID: {self.user.id})")
            print("------")
            self.ready_event_fired = True  # Set flag to prevent re-execution

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

        # Process commands (if any)
        await self.process_commands(message)

        # Example: Respond to a specific message
        if "hello bot" in message.content.lower():
            await message.channel.send(f"Hello, {message.author.display_name}!")

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
            else:
                print(f"Error: Channel with ID {channel_id} not found or inaccessible.")
        except Exception as e:
            print(f"Error sending message to channel {channel_id}: {e}")

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
            else:
                print(f"Error: User with ID {user_id} not found.")
        except Exception as e:
            print(f"Error sending direct message to user {user_id}: {e}")

    async def send_jeopardy_question(
        self, target_id, is_channel, category, value, question
    ):
        """
        Sends a Jeopardy! question to a specified Discord channel or user.

        Args:
            target_id (int): The ID of the channel or user.
            is_channel (bool): True if target_id is a channel ID, False if a user ID.
            category (str): The category of the Jeopardy! question.
            value (int or str): The point value of the question.
            question (str): The Jeopardy! question text.
        """
        message_body = f"Jeopardy! Question:\nCategory: {category}\nValue: ${value}\nQuestion: {question}"
        print(
            f"Attempting to send Jeopardy question to {'channel' if is_channel else 'user'} ID {target_id}..."
        )
        if is_channel:
            await self.send_message_to_channel(target_id, message_body)
        else:
            await self.send_message_to_user(target_id, message_body)

    async def send_jeopardy_answer(
        self, target_id, is_channel, category, value, question, answer
    ):
        """
        Sends the answer to a Jeopardy! question to a specified Discord channel or user.

        Args:
            target_id (int): The ID of the channel or user.
            is_channel (bool): True if target_id is a channel ID, False if a user ID.
            category (str): The category of the Jeopardy! question.
            value (int or str): The point value of the question.
            question (str): The original Jeopardy! question text.
            answer (str): The correct answer to the question.
        """
        message_body = (
            f"Jeopardy! Answer Time!\n"
            f"Category: {category}\n"
            f"Value: ${value}\n"
            f"Question: {question}\n"
            f"Correct Answer: {answer}"
        )
        print(
            f"Attempting to send Jeopardy answer to {'channel' if is_channel else 'user'} ID {target_id}..."
        )
        if is_channel:
            await self.send_message_to_channel(target_id, message_body)
        else:
            await self.send_message_to_user(target_id, message_body)

    # Start the bot in a separate asynchronous function
    async def main(self):
        # Wait for the bot to be ready before sending messages
        print("\n--- Waiting until ready ---")
        await self.wait_until_ready()
        print("\n--- Testing send_message_to_channel ---")
        await self.send_message_to_user(
            config.get("DISCORD_USER_ID"),
            "This is a test message from the bot!",
        )

        print("\n--- Testing send_jeopardy_question to channel ---")
        await self.send_jeopardy_question(
            target_id=config.get("DISCORD_USER_ID"),
            is_channel=True,
            category="test category",
            value="test value",
            question="test question",
        )

        print("\n--- Testing send_jeopardy_answer to user (DM) ---")
        await self.send_jeopardy_answer(
            target_id=config.get("DISCORD_USER_ID"),
            is_channel=False,
            category="test category",
            value="test value",
            question="test question",
            answer="test answer",
        )


def test_discord_bot(config: ConfigReader, questions: list):
    import asyncio

    # Load configuration
    async def run_discord_bot():
        # Initialize the bot
        bot = DiscordBot(config.get("DISCORD_BOT_TOKEN"))

        @bot.command(name="shutdown")
        async def shutdown(ctx):
            if await bot.is_owner(
                ctx.author
            ):  # Ensure only the bot owner can shut down
                print("Shutting down bot...")
                await bot.close()
            else:
                await ctx.send("You do not have permission to shut down the bot.")

        @bot.command(name="ping")
        async def ping(self, ctx):
            """Responds with 'Pong!' to test bot latency."""
            await ctx.send("Pong!")

        # You can add commands here if needed, or other event listeners
        @bot.command(name="dailyquestion")
        async def daily_question_command(ctx):
            # This command could trigger sending the daily Jeopardy question
            await ctx.send("Fetching today's Jeopardy question...")
            # In a real scenario, you'd fetch a question and then send it
            random_q = get_random_question(questions)
            await bot.send_jeopardy_question(
                config.get('DISCORD_USER_ID'),
                False,
                random_q['category'],
                random_q['clue_value'],
                random_q['answer']
            )
            time.sleep(10)
            await bot.send_jeopardy_answer(
                config.get('DISCORD_USER_ID'),
                False,
                random_q['category'],
                random_q['clue_value'],
                random_q['answer'],
                random_q['question']
            )

        # Start the bot
        await bot.start(bot.bot_token)
        
    # Run the asynchronous function
    asyncio.run(run_discord_bot())
