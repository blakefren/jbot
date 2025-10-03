from discord.ext import commands
from modes.powerup import PowerUpManager


class Powerup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _get_powerup_manager(self, interaction):
        if self.bot.game.mode.name != "POWERUP":
            await self.bot.send_message(
                "This command is only available in POWERUP mode.",
                interaction=interaction,
                ephemeral=True,
            )
            return None

        players = self.bot.game.logger.get_guess_metrics(
            [], self.bot.game.question_selector.questions
        ).get("players", {})
        return PowerUpManager(players)

    @commands.hybrid_command(name="wager")
    async def wager(self, ctx: commands.Context, amount: int):
        """Wager points for the current question (POWERUP mode only)."""
        manager = await self._get_powerup_manager(ctx.interaction)
        if manager:
            result = manager.wager_points(str(ctx.author.id), amount)
            await self.bot.send_message(result, interaction=ctx.interaction)

    @commands.hybrid_command(name="boss_fight")
    async def boss_fight(self, ctx: commands.Context):
        """Placeholder for weekly boss fight."""
        await self.bot.send_message(
            "This command is not yet implemented.",
            interaction=ctx.interaction,
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Powerup(bot))
