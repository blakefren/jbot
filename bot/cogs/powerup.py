from discord.ext import commands
from bot.cogs.utils import get_powerup_manager


class Powerup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="wager")
    async def wager(self, ctx: commands.Context, amount: int):
        """Wager points for the current question (POWERUP mode only)."""
        manager = await get_powerup_manager(self.bot, ctx.interaction)
        if manager:
            result = manager.wager_points(str(ctx.author.id), amount)
            await self.bot.send_message(result, interaction=ctx.interaction)

    @commands.command(name="boss_fight")
    async def boss_fight(self, ctx: commands.Context):
        """Placeholder for weekly boss fight."""
        await self.bot.send_message(
            "This command is not yet implemented.",
            interaction=ctx.interaction,
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Powerup(bot))
