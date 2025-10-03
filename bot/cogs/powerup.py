import discord
from discord.ext import commands

from modes.powerup import PowerUpManager

class Powerup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="wager")
    async def wager(self, ctx: commands.Context, amount: int):
        """Wager points for the current question (POWERUP mode only)."""
        if self.bot.game.mode.name != "POWERUP":
            await self.bot.send_message(
                "Wagering is only available in POWERUP mode.",
                interaction=ctx.interaction,
                ephemeral=True,
            )
            return
        players = self.bot.game.logger.get_guess_metrics(
            [], self.bot.game.question_selector.questions
        ).get("players", {})
        manager = PowerUpManager(players)
        result = manager.wager_points(str(ctx.author.id), amount)
        await self.bot.send_message(result, interaction=ctx.interaction)

    @commands.hybrid_command(name="weekly_boss_fight")
    async def weekly_boss_fight(self, ctx: commands.Context):
        """Placeholder for weekly boss fight."""
        await self.bot.send_message(
            "This command is not yet implemented.",
            interaction=ctx.interaction,
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Powerup(bot))
