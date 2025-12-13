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

    @power.command(name="disrupt", description="Break another player's answer streak.")
    async def disrupt(self, ctx: commands.Context, target_id: str):
        """Break another player's answer streak."""
        if not self.bot.game.features.get("fight"):
            await self.bot.send_message(
                "Fight track is not enabled.",
                interaction=ctx.interaction,
                ephemeral=True,
            )
            return

        manager = self._get_manager()
        if manager:
            result = manager.disrupt(str(ctx.author.id), target_id)
            await self.bot.send_message(result, interaction=ctx.interaction)

    @power.command(name="shield", description="Block the next attack against you.")
    async def shield(self, ctx: commands.Context):
        """Block the next attack against you."""
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
            await self.bot.send_message(result, interaction=ctx.interaction)

    @power.command(name="steal", description="Steal points from another player.")
    async def steal(self, ctx: commands.Context, target_id: str):
        """Steal points from another player."""
        if not self.bot.game.features.get("fight"):
            await self.bot.send_message(
                "Fight track is not enabled.",
                interaction=ctx.interaction,
                ephemeral=True,
            )
            return

        manager = self._get_manager()
        if manager:
            result = manager.steal(str(ctx.author.id), target_id)
            await self.bot.send_message(result, interaction=ctx.interaction)

    @power.command(name="wager", description="Wager points on the current question.")
    async def wager(self, ctx: commands.Context, amount: int):
        """Wager points on the current question."""
        if not self.bot.game.features.get("powerup"):
            await self.bot.send_message(
                "Power-up track is not enabled.",
                interaction=ctx.interaction,
                ephemeral=True,
            )
            return

        manager = self._get_manager()
        if manager:
            result = manager.place_wager(str(ctx.author.id), amount)
            await self.bot.send_message(result, interaction=ctx.interaction)

    @power.command(name="reinforce", description="Reinforce another player.")
    async def reinforce(self, ctx: commands.Context, target_id: str):
        """Reinforce another player."""
        if not self.bot.game.features.get("coop"):
            await self.bot.send_message(
                "Coop track is not enabled.",
                interaction=ctx.interaction,
                ephemeral=True,
            )
            return

        manager = self._get_manager()
        if manager:
            result = manager.reinforce(str(ctx.author.id), target_id)
            await self.bot.send_message(result, interaction=ctx.interaction)

    @power.command(name="reveal", description="Reveal letters in the answer.")
    async def reveal(self, ctx: commands.Context):
        """Reveal letters in the answer."""
        if not self.bot.game.features.get("coop"):
            await self.bot.send_message(
                "Coop track is not enabled.",
                interaction=ctx.interaction,
                ephemeral=True,
            )
            return

        # Reveal is not implemented in PowerUpManager yet.
        await self.bot.send_message(
            "This command is not yet implemented.",
            interaction=ctx.interaction,
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Power(bot))
