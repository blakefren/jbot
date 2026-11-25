from discord.ext import commands
from src.core.guess_display import process_guess


class Trivia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command()
    async def answer(self, ctx: commands.Context, *, guess: str):
        """Answer the current daily question."""
        # Defer the response to prevent timeouts, making it ephemeral so only the user sees it.
        await ctx.interaction.response.defer(ephemeral=True)

        outcome = process_guess(
            self.bot.game,
            ctx.author.id,
            ctx.author.display_name,
            guess,
            ctx.author.mention,
        )
        await ctx.interaction.followup.send(outcome.private_message)
        if outcome.public_message:
            await ctx.channel.send(outcome.public_message)


async def setup(bot):
    await bot.add_cog(Trivia(bot))
