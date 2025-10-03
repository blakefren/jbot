import discord
from discord.ext import commands
from bot.subscriber import Subscriber

class Trivia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="question", aliases=["q", "query"])
    async def question(self, ctx: commands.Context):
        """Get a random question and answer."""
        random_q = self.bot.game.question_selector.get_random_question()
        if not random_q:
            await self.bot.send_message(
                "Could not find a question.",
                interaction=ctx.interaction,
                ephemeral=True,
            )
            return

        question_part = self.bot.game.format_question(random_q)
        answer_part = self.bot.game.format_answer(random_q)
        full_message = f"{question_part}\n{answer_part}"
        await self.bot.send_message(full_message, interaction=ctx.interaction)

    @commands.hybrid_command(name="when", aliases=["next", "howlong"])
    async def when(self, ctx: commands.Context):
        """Get the next event time. Shows the active question, if there is one."""
        morning_time_next = self.bot.morning_message_task.next_iteration
        evening_time_next = self.bot.evening_message_task.next_iteration
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
        await self.bot.send_message(
            response_content, interaction=ctx.interaction
        )

        # Remind the daily question, if after the morning send time.
        if self.bot.game.daily_q:
            question_part = self.bot.game.format_question(self.bot.game.daily_q)
            await self.bot.send_message(
                question_part, interaction=ctx.interaction
            )

    @commands.hybrid_command(name="answer", aliases=["a", "ans"])
    async def answer(self, ctx: commands.Context, *, guess: str):
        """Submits an answer for the current daily question."""
        if not self.bot.game.daily_q:
            # For test context, use ctx, not interaction
            await self.bot.send_message(
                "There is no active question right now.",
                interaction=ctx.interaction,
                ephemeral=True,
            )
            return

        player_id = ctx.author.id
        player_name = ctx.author.display_name
        is_correct = self.bot.game.handle_guess(player_id, player_name, guess)

        # Log the guess submission event
        status = "correct_guess" if is_correct else "incorrect_guess"
        self.bot.logger.log_messaging_event(
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
        await self.bot.send_message(
            response_content,
            interaction=ctx.interaction,
            ephemeral=True,
        )

    @commands.hybrid_command(name="subscribe", aliases=["sub"])
    async def subscribe(self, ctx: commands.Context):
        """Subscribes the context to daily question notifications."""
        subscriber = Subscriber.from_ctx(ctx)
        if subscriber in self.bot.game.get_subscribed_users():
            response_content = (
                f"Participant {subscriber.display_name}, you are already registered."
            )
            await self.bot.send_message(
                response_content,
                interaction=ctx.interaction,
                ephemeral=True,
                success_status="already_subscribed",
            )
        else:
            self.bot.game.add_subscriber(subscriber)
            response_content = (
                f"Participant {subscriber.display_name}, you are now registered for the daily games.\n"
                f"{len(self.bot.game.get_subscribed_users())} players are now in play."
            )
            await self.bot.send_message(
                response_content,
                interaction=ctx.interaction,
                success_status="subscribed",
            )

    @commands.hybrid_command(name="unsubscribe", aliases=["unsub"])
    async def unsubscribe(self, ctx: commands.Context):
        """Unsubscribes the context from daily question notifications."""
        subscriber = Subscriber.from_ctx(ctx)
        if subscriber in self.bot.game.get_subscribed_users():
            self.bot.game.remove_subscriber(subscriber)
            response_content = (
                f"Participant {subscriber.display_name}, you have been removed from the games.\n"
                f"There are {len(self.bot.game.get_subscribed_users())} players remaining."
            )
            await self.bot.send_message(
                response_content,
                interaction=ctx.interaction,
                success_status="unsubscribed",
            )
        else:
            response_content = (
                f"Participant {subscriber.display_name}, you were not registered for the games.\n"
                f"There are still {len(self.bot.game.get_subscribed_users())} players in play."
            )
            await self.bot.send_message(
                response_content,
                interaction=ctx.interaction,
                ephemeral=True,
                success_status="not_subscribed",
            )


async def setup(bot):
    await bot.add_cog(Trivia(bot))
