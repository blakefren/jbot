from discord.ext import commands


class Metrics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command()
    async def history(self, ctx: commands.Context):
        """View your game history and stats."""
        player_id = ctx.author.id
        player_name = ctx.author.display_name
        history_text = self.bot.game.get_player_history(player_id, player_name)
        await self.bot.send_message(
            history_text, interaction=ctx.interaction, ephemeral=True
        )

    @commands.hybrid_command()
    async def leaderboard(self, ctx: commands.Context):
        """View the current score leaderboard."""
        leaderboard = self.bot.game.get_scores_leaderboard(ctx.guild)
        await self.bot.send_message(leaderboard, interaction=ctx.interaction)


async def setup(bot):
    await bot.add_cog(Metrics(bot))
