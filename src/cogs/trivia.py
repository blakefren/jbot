from discord.ext import commands
import logging

from src.core.guess_handler import AlreadyAnsweredCorrectlyError


class Trivia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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
            (
                is_correct,
                num_guesses,
                points_earned,
                bonus_messages,
            ) = self.bot.game.handle_guess(player_id, player_name, guess)
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
            # Construct bonus string
            bonus_str = ""
            if bonus_messages:
                bonus_str = "\n" + "\n".join(f"{msg}" for msg in bonus_messages)

            # Send the private confirmation
            await ctx.interaction.followup.send(
                f"That is correct! Nicely done.\n\n" f"Your guesses:\n{guesses_text}"
            )
            # Announce the correct answer publicly in the channel
            await ctx.channel.send(
                f"{ctx.author.mention} got the correct answer in {num_guesses} guess(es)!\n"
                f"They earned **{points_earned}** points!{bonus_str}"
            )
        else:
            # Send the private confirmation for an incorrect answer
            await ctx.interaction.followup.send(
                f"Sorry, that is not the correct answer.\n\nYour guesses:\n{guesses_text}"
            )


async def setup(bot):
    await bot.add_cog(Trivia(bot))
