from discord.ext import commands
import logging

from src.core.game_runner import AlreadyAnsweredCorrectlyError


class Trivia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command()
    async def question(self, ctx: commands.Context):
        """Get a random trivia question."""
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
        # Add hint if present
        hint_part = (
            f"\nHint: ||**{random_q.hint}**||"
            if getattr(random_q, "hint", None)
            else ""
        )
        full_message = f"{question_part}{hint_part}\n{answer_part}"
        await self.bot.send_message(full_message, interaction=ctx.interaction)

    @commands.hybrid_command()
    async def when(self, ctx: commands.Context):
        """Next event time & current question."""
        morning_task = self.bot.morning_message_task
        evening_task = self.bot.evening_message_task

        if not morning_task.is_running() or not evening_task.is_running():
            await self.bot.send_message(
                "Tasks are not running.", interaction=ctx.interaction, ephemeral=True
            )
            return

        morning_time_next = morning_task.next_iteration
        evening_time_next = evening_task.next_iteration

        if morning_time_next < evening_time_next:
            event_name = "next question"
            next_datetime = morning_time_next
        else:
            event_name = "answer reveal"
            next_datetime = evening_time_next

        response_content = (
            f"The {event_name} is <t:{int(next_datetime.timestamp())}:R> "
            f"(at <t:{int(next_datetime.timestamp())}:T>)."
        )

        # If there's an active question, show it.
        if self.bot.game.daily_q and morning_time_next > evening_time_next:
            response_content += (
                "\n\n**Today's Question:**\n"
                + self.bot.game.format_question(self.bot.game.daily_q)
            )

        await self.bot.send_message(
            response_content, interaction=ctx.interaction, ephemeral=True
        )

    @commands.hybrid_command()
    async def answer(self, ctx: commands.Context, *, guess: str):
        """Answer the current daily question."""
        # Defer the response to prevent timeouts, making it ephemeral so only the user sees it.
        await ctx.interaction.response.defer(ephemeral=True)

        if not self.bot.game.daily_q:
            await ctx.interaction.followup.send(
                "There is no active question right now."
            )
            return

        try:
            player_id = ctx.author.id
            player_name = ctx.author.display_name
            is_correct, num_guesses = self.bot.game.handle_guess(
                player_id, player_name, guess
            )
        except AlreadyAnsweredCorrectlyError:
            await ctx.interaction.followup.send(
                "You have already answered today's question correctly."
            )
            return
        except Exception as e:
            logging.error(f"Error handling guess: {e}")
            await ctx.interaction.followup.send(
                "An error occurred while processing your answer. Please try again later."
            )
            return

        # Retrieve all guesses for this player for the current question
        daily_question_id = self.bot.game.daily_question_id
        if not daily_question_id:
            all_guesses = []
        else:
            guesses = self.bot.game.data_manager.read_guess_history(user_id=player_id)
            all_guesses = [
                g.get("guess_text")
                for g in guesses
                if g.get("daily_question_id") == daily_question_id
            ]

        # Deduplicate and sort guesses
        unique_guesses = sorted({(g or "").lower() for g in all_guesses})
        guesses_text = (
            "\n".join(f"{i+1}. {g}" for i, g in enumerate(unique_guesses))
            if unique_guesses
            else "No guesses yet."
        )

        # Send a confirmation message
        if is_correct:
            # Send the private confirmation
            await ctx.interaction.followup.send(
                f"That is correct! Nicely done.\n\nYour guesses:\n{guesses_text}"
            )
            # Announce the correct answer publicly in the channel
            await ctx.channel.send(
                f"{ctx.author.mention} got the correct answer in {num_guesses} guess(es)!"
            )
        else:
            # Send the private confirmation for an incorrect answer
            await ctx.interaction.followup.send(
                f"Sorry, that is not the correct answer.\n\nYour guesses:\n{guesses_text}"
            )


async def setup(bot):
    await bot.add_cog(Trivia(bot))
