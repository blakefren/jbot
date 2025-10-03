import discord
from discord.ext import commands

from modes.powerup import PowerUpManager


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
        players = self.bot.game.logger.get_guess_metrics(
            [], self.bot.game.question_selector.questions
        ).get("players", {})
        manager = PowerUpManager(players)
        result = manager.reinforce(str(ctx.author.id), target_id)
        await self.bot.send_message(result, interaction=ctx.interaction)

    @commands.hybrid_command(name="reveal_answer_letters")
    async def reveal_answer_letters(self, ctx: commands.Context):
        """Placeholder for revealing answer letters."""
        await self.bot.send_message(
            "This command is not yet implemented.",
            interaction=ctx.interaction,
            ephemeral=True,
        )

    @commands.hybrid_command(name="red_vs_blue_teams")
    async def red_vs_blue_teams(self, ctx: commands.Context):
        """Placeholder for red vs blue teams."""
        await self.bot.send_message(
            "This command is not yet implemented.",
            interaction=ctx.interaction,
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Coop(bot))
