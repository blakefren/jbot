from discord.ext import commands
from bot.cogs.utils import get_powerup_manager


class Fight(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="disrupt")
    async def disrupt(self, ctx: commands.Context, target_id: str):
        """Break another player's answer streak (POWERUP mode only)."""
        manager = await get_powerup_manager(self.bot, ctx.interaction)
        if manager:
            result = manager.disrupt(str(ctx.author.id), target_id)
            await self.bot.send_message(result, interaction=ctx.interaction)

    @commands.command(name="shield")
    async def shield(self, ctx: commands.Context):
        """Activate a shield to block the next attack (POWERUP mode only)."""
        manager = await get_powerup_manager(self.bot, ctx.interaction)
        if manager:
            result = manager.use_shield(str(ctx.author.id))
            await self.bot.send_message(result, interaction=ctx.interaction)

    @commands.command(name="steal")
    async def steal(self, ctx: commands.Context, target_id: str):
        """Steal half of another player's points earned today (POWERUP mode only)."""
        manager = await get_powerup_manager(self.bot, ctx.interaction)
        if manager:
            result = manager.steal(str(ctx.author.id), target_id)
            await self.bot.send_message(result, interaction=ctx.interaction)


async def setup(bot):
    await bot.add_cog(Fight(bot))
