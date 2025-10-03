import discord
from discord.ext import commands

from modes.powerup import PowerUpManager

class Fight(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="disrupt", aliases=["disruptstreak", "disrupt_streak"])
    async def disrupt(self, ctx: commands.Context, target_id: str):
        """Break another player's answer streak (POWERUP mode only)."""
        if self.bot.game.mode.name != "POWERUP":
            await self.bot.send_message(
                "Disrupt is only available in POWERUP mode.",
                interaction=ctx.interaction,
                ephemeral=True,
            )
            return
        players = self.bot.game.logger.get_guess_metrics(
            [], self.bot.game.question_selector.questions
        ).get("players", {})
        manager = PowerUpManager(players)
        result = manager.disrupt(str(ctx.author.id), target_id)
        await self.bot.send_message(result, interaction=ctx.interaction)

    @commands.hybrid_command(name="shield")
    async def shield(self, ctx: commands.Context):
        """Activate a shield to block the next attack (POWERUP mode only)."""
        if self.bot.game.mode.name != "POWERUP":
            await self.bot.send_message(
                "Shield is only available in POWERUP mode.",
                interaction=ctx.interaction,
                ephemeral=True,
            )
            return
        players = self.bot.game.logger.get_guess_metrics(
            [], self.bot.game.question_selector.questions
        ).get("players", {})
        manager = PowerUpManager(players)
        result = manager.use_shield(str(ctx.author.id))
        await self.bot.send_message(result, interaction=ctx.interaction)

    @commands.hybrid_command(name="steal")
    async def steal(self, ctx: commands.Context, target_id: str):
        """Steal half of another player's points earned today (POWERUP mode only)."""
        if self.bot.game.mode.name != "POWERUP":
            await self.bot.send_message(
                "Steal is only available in POWERUP mode.",
                interaction=ctx.interaction,
                ephemeral=True,
            )
            return
        players = self.bot.game.logger.get_guess_metrics(
            [], self.bot.game.question_selector.questions
        ).get("players", {})
        manager = PowerUpManager(players)
        result = manager.steal(str(ctx.author.id), target_id)
        await self.bot.send_message(result, interaction=ctx.interaction)


async def setup(bot):
    await bot.add_cog(Fight(bot))
