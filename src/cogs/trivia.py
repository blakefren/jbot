from discord.ext import commands
import logging
from src.cfg.main import ConfigReader

from src.core.guess_handler import AlreadyAnsweredCorrectlyError, JinxedError


class Trivia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command()
    async def answer(self, ctx: commands.Context, *, guess: str):
        """Answer the current daily question."""
        # Defer the response to prevent timeouts, making it ephemeral so only the user sees it.
        await ctx.interaction.response.defer(ephemeral=True)

        if not self.bot.game.daily_q:
            await ctx.interaction.followup.send("There is no active question.")
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
            await ctx.interaction.followup.send("You already solved today.")
            return
        except JinxedError as e:
            emoji_silenced = ConfigReader().get("JBOT_EMOJI_SILENCED", "🤐")
            await ctx.interaction.followup.send(f"{emoji_silenced} {e.message}")
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
                f"Correct! Nicely done.\n\nGuesses:\n{guesses_text}"
            )
            # Announce the correct answer publicly in the channel
            await ctx.channel.send(
                f"{ctx.author.mention} solved it in {num_guesses}! (+**{points_earned}** pts){bonus_str}"
            )
        else:
            # Send the private confirmation for an incorrect answer
            await ctx.interaction.followup.send(
                f"Sorry, that was incorrect.\n\nGuesses:\n{guesses_text}"
            )


async def setup(bot):
    await bot.add_cog(Trivia(bot))
