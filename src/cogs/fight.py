from discord.ext import commands
from src.cogs.utils import get_powerup_manager


class Fight(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command()
    async def disrupt(self, ctx: commands.Context, target_id: str):
        """Break another player's answer streak."""
        manager = await get_powerup_manager(self.bot, ctx.interaction)
        if manager:
            result = manager.disrupt(str(ctx.author.id), target_id)
            await self.bot.send_message(result, interaction=ctx.interaction)

    @commands.hybrid_command()
    async def shield(self, ctx: commands.Context):
        """Block the next attack against you."""
        manager = await get_powerup_manager(self.bot, ctx.interaction)
        if manager:
            result = manager.use_shield(str(ctx.author.id))
            await self.bot.send_message(result, interaction=ctx.interaction)

    @commands.hybrid_command()
    async def steal(self, ctx: commands.Context, target_id: str):
        """Steal points from another player."""
        manager = await get_powerup_manager(self.bot, ctx.interaction)
        if manager:
            result = manager.steal(str(ctx.author.id), target_id)
            await self.bot.send_message(result, interaction=ctx.interaction)


async def setup(bot):
    await bot.add_cog(Fight(bot))
