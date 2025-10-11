import os
import sys

from discord.ext import commands

from src.cfg.players import read_players_into_dict
from src.core.powerup import PowerUpManager


async def get_powerup_manager(bot, interaction):
    if bot.game.mode.name != "POWERUP":
        await bot.send_message(
            "This command is only available in POWERUP mode.",
            interaction=interaction,
            ephemeral=True,
        )
        return None

    players = read_players_into_dict()
    return PowerUpManager(players)


class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command()
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

    @commands.hybrid_command()
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

    @commands.hybrid_command()
    async def ping(self, ctx: commands.Context):
        """Check the bot's response time."""
        response_content = "Pong!"
        await self.bot.send_message(response_content, interaction=ctx.interaction)


async def setup(bot):
    await bot.add_cog(Utils(bot))
