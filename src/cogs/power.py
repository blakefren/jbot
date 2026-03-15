import discord
from discord.ext import commands
from src.core.powerup import PowerUpError, STEAL_STREAK_COST


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
            try:
                result = manager.jinx(
                    str(ctx.author.id), str(target.id), self.bot.game.daily_question_id
                )
                await self.bot.send_message(
                    result, interaction=ctx.interaction, ephemeral=True
                )
            except PowerUpError as e:
                await self.bot.send_message(
                    str(e), interaction=ctx.interaction, ephemeral=True
                )

    @power.command(
        name="rest",
        description="Skip today, keep your streak, earn a point bonus tomorrow.",
    )
    async def rest(self, ctx: commands.Context):
        if not self.bot.game.daily_q:
            await self.bot.send_message(
                "There is no active question right now.",
                interaction=ctx.interaction,
                ephemeral=True,
            )
            return

        manager = self._get_manager()
        if manager:
            try:
                public_msg, private_msg = manager.rest(
                    str(ctx.author.id),
                    self.bot.game.daily_question_id,
                    self.bot.game.daily_q.answer,
                )
                # Send public announcement to the channel
                await self.bot.send_message(public_msg, interaction=ctx.interaction)
                # Send private answer disclosure (ephemeral for slash, DM for text)
                if ctx.interaction:
                    await self.bot.send_message(
                        private_msg, interaction=ctx.interaction, ephemeral=True
                    )
                else:
                    await ctx.author.send(private_msg)
            except Exception as e:
                await self.bot.send_message(
                    str(e), interaction=ctx.interaction, ephemeral=True
                )

    @power.command(
        name="steal",
        description=f"Steal bonuses from a target, but lose {STEAL_STREAK_COST} streak days.",
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
            try:
                result = manager.steal(
                    str(ctx.author.id), str(target.id), self.bot.game.daily_question_id
                )
                await self.bot.send_message(
                    result, interaction=ctx.interaction, ephemeral=True
                )
            except PowerUpError as e:
                await self.bot.send_message(
                    str(e), interaction=ctx.interaction, ephemeral=True
                )


async def setup(bot):
    await bot.add_cog(Power(bot))
