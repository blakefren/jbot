import os
import sys

from discord.ext import commands

from bot.managers.powerup import PowerUpManager


async def get_powerup_manager(bot, interaction):
    if bot.game.mode.name != "POWERUP":
        await bot.send_message(
            "This command is only available in POWERUP mode.",
            interaction=interaction,
            ephemeral=True,
        )
        return None

    players = bot.game.logger.get_guess_metrics(
        [], bot.game.question_selector.questions
    ).get("players", {})
    return PowerUpManager(players)


class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="shutdown")
    @commands.is_owner()
    async def shutdown(self, ctx: commands.Context):
        """Shuts down the bot."""
        print("Shutting down...")
        await self.bot.send_message("Shutting down...", interaction=ctx.interaction)

        # Stop background tasks
        for task in [
            self.bot.morning_message_task,
            self.bot.reminder_message_task,
            self.bot.evening_message_task,
        ]:
            if task.is_running():
                task.cancel()

        # Close the database connection before shutting down the bot
        if hasattr(self.bot, "db") and self.bot.db.conn:
            self.bot.db.close()

        await self.bot.close()
        sys.exit(0)

    @shutdown.error
    async def shutdown_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send(
                "You do not have permission to shut down the bot.", ephemeral=True
            )
        else:
            await ctx.send(f"An error occurred: {error}", ephemeral=True)

    @commands.hybrid_command(name="restart")
    @commands.is_owner()
    async def restart(self, ctx: commands.Context):
        """Restarts the bot."""
        print("Restarting bot...")
        # Create restart info file to be read on next startup
        with open("restart.inf", "w") as f:
            f.write(f"{ctx.channel.id},{ctx.author.id}")
        await self.bot.send_message("Restarting bot...", interaction=ctx.interaction)
        
        # Close the database connection before shutting down the bot
        if hasattr(self.bot, "db") and self.bot.db.conn:
            self.bot.db.close()

        await self.bot.close()
        os.execv(sys.executable, ["python"] + sys.argv)

    @restart.error
    async def restart_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send(
                "You do not have permission to restart the bot.", ephemeral=True
            )
        else:
            await ctx.send(f"An error occurred during restart: {error}", ephemeral=True)
            if os.path.exists("restart.inf"):
                os.remove("restart.inf")

    @commands.hybrid_command(name="ping")
    async def ping(self, ctx: commands.Context):
        """Responds with 'Pong!' to test bot latency."""
        response_content = "Pong!"
        await self.bot.send_message(response_content, interaction=ctx.interaction)


async def setup(bot):
    await bot.add_cog(Utils(bot))
