from discord.ext import commands


class Coop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="reinforce")
    async def reinforce(self, ctx: commands.Context, target_id: str):
        """Reinforce another player for the day (COOP mode only)."""
        if self.bot.game.mode.name != "COOP":
            await self.bot.send_message(
                "Reinforce is only available in COOP mode.",
                interaction=ctx.interaction,
                ephemeral=True,
            )
            return
        # TODO: Implement reinforce logic
        await self.bot.send_message(
            "This command is not yet implemented.",
            interaction=ctx.interaction,
            ephemeral=True,
        )

    @commands.hybrid_command(name="reveal")
    async def reveal(self, ctx: commands.Context):
        """Placeholder for revealing answer letters."""
        await self.bot.send_message(
            "This command is not yet implemented.",
            interaction=ctx.interaction,
            ephemeral=True,
        )

    @commands.hybrid_command(name="teams")
    async def teams(self, ctx: commands.Context):
        """Placeholder for red vs blue teams."""
        await self.bot.send_message(
            "This command is not yet implemented.",
            interaction=ctx.interaction,
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Coop(bot))
