import os
import sys

from discord.ext import commands


class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="shutdown", aliases=["quit", "exit"])
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

        await self.bot.close()

    @shutdown.error
    async def shutdown_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send(
                "You do not have permission to shut down the bot.", ephemeral=True
            )
        else:
            await ctx.send(f"An error occurred: {error}", ephemeral=True)

    @commands.hybrid_command(name="restart", aliases=["reboot", "r", "reset"])
    @commands.is_owner()
    async def restart(self, ctx: commands.Context):
        """Restarts the bot."""
        print("Restarting bot...")
        # Create restart info file to be read on next startup
        with open("restart.inf", "w") as f:
            f.write(f"{ctx.channel.id},{ctx.author.id}")
        await self.bot.send_message("Restarting bot...", interaction=ctx.interaction)
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
