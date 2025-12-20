import discord
from discord.ext import commands


class Power(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(name="power", description="Use game powers.")
    async def power(self, ctx: commands.Context):
        """Use game powers."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    def _get_manager(self):
        return self.bot.game.managers.get("powerup")

    @power.command(
        name="jinx",
        description="Prevents streak bonus, but you can't answer until the hint.",
    )
    async def jinx(self, ctx: commands.Context, target: discord.Member):
        if not self.bot.game.features.get("fight"):
            await self.bot.send_message(
                "Fight track is not enabled.",
                interaction=ctx.interaction,
                ephemeral=True,
            )
            return

        manager = self._get_manager()
        if manager:
            result = manager.jinx(str(ctx.author.id), str(target.id))
            await self.bot.send_message(result, interaction=ctx.interaction)

    @power.command(
        name="shield",
        description="Reflect attacks, but lose points if you aren't attacked.",
    )
    async def shield(self, ctx: commands.Context):
        if not self.bot.game.features.get("fight"):
            await self.bot.send_message(
                "Fight track is not enabled.",
                interaction=ctx.interaction,
                ephemeral=True,
            )
            return

        manager = self._get_manager()
        if manager:
            result = manager.use_shield(str(ctx.author.id))
            await self.bot.send_message(
                result, interaction=ctx.interaction, ephemeral=True
            )

    @power.command(
        name="steal", description="Steal fastest/first bonuses , but break your streak."
    )
    async def steal(self, ctx: commands.Context, target: discord.Member):
        if not self.bot.game.features.get("fight"):
            await self.bot.send_message(
                "Fight track is not enabled.",
                interaction=ctx.interaction,
                ephemeral=True,
            )
            return

        manager = self._get_manager()
        if manager:
            result = manager.steal(str(ctx.author.id), str(target.id))
            await self.bot.send_message(result, interaction=ctx.interaction)


async def setup(bot):
    await bot.add_cog(Power(bot))
