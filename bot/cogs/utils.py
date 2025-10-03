import asyncio
import os
import sys

import discord
from discord.ext import commands


class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="shutdown", aliases=["quit", "exit"])
    async def shutdown(self, ctx: commands.Context):
        """Shuts down the bot."""
        if not await self.bot.is_owner(ctx.author):
            response_content = "You do not have permission to shut down the bot."
            await self.bot.send_message(
                response_content,
                interaction=ctx.interaction,
                ephemeral=True,
                success_status="unauthorized",
            )
            return

        print("Shutting down...")
        try:
            await self.bot.send_message(
                "Shutting down...", interaction=ctx.interaction
            )
        except Exception as e:
            print(f"Failed to send shutdown message: {e}")
            self.bot.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender=str(ctx.author.id),
                content=f"Failed to send shutdown message: {e}",
                status="message_send_failed",
            )

        # Stop the tasks gracefully
        if self.bot.morning_message_task.is_running():
            self.bot.morning_message_task.stop()
            print("Morning task stopped.")
        if self.bot.reminder_message_task.is_running():
            self.bot.reminder_message_task.stop()
            print("Reminder task stopped.")
        if self.bot.evening_message_task.is_running():
            self.bot.evening_message_task.stop()
            print("Evening task stopped.")

        await asyncio.sleep(0.1)

        if hasattr(self.bot.http, "session") and not self.bot.http.session.closed:
            try:
                await self.bot.http.session.close()
                print("aiohttp session closed.")
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"Error closing aiohttp session: {e}")
                self.bot.logger.log_messaging_event(
                    direction="bot",
                    method="Discord",
                    recipient_or_sender="N/A",
                    content=f"Error closing aiohttp session during shutdown: {e}",
                    status="aiohttp_close_failed",
                )

        # TODO: should we close the logger here?
        try:
            await self.bot.close()
            print("Bot closed successfully.")
            self.bot.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender=str(ctx.author.id),
                content="Bot gracefully shut down.",
                status="completed",
            )
        except Exception as e:
            print(f"Error during bot.close(): {e}")
            self.bot.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender=str(ctx.author.id),
                content=f"Error during bot.close(): {e}",
                status="bot_close_failed",
            )

    @commands.hybrid_command(name="restart", aliases=["reboot", "r", "reset"])
    async def restart(self, ctx: commands.Context):
        """Restarts the bot."""
        if not await self.bot.is_owner(ctx.author):
            response_content = "You do not have permission to restart the bot."
            await self.bot.send_message(
                response_content,
                interaction=ctx.interaction,
                ephemeral=True,
                success_status="unauthorized",
            )
            return

        print("Restarting bot...")
        try:
            # Create restart info file to be read on next startup
            with open("restart.inf", "w") as f:
                f.write(f"{ctx.channel.id},{ctx.author.id}")
            await self.bot.send_message(
                "Restarting bot...", interaction=ctx.interaction
            )

            # Cleanly close the bot before restarting
            await self.bot.close()

            # Replace the current process with a new one
            os.execv(sys.executable, ["python"] + sys.argv)

        except Exception as e:
            print(f"Failed to restart bot: {e}")
            self.bot.logger.log_messaging_event(
                direction="bot",
                method="Discord",
                recipient_or_sender=str(ctx.author.id),
                content=f"Failed to restart bot: {e}",
                status="restart_failed",
            )
            # Clean up if something went wrong before restart
            if os.path.exists("restart.inf"):
                os.remove("restart.inf")

    @commands.hybrid_command(name="ping")
    async def ping(self, ctx: commands.Context):
        """Responds with 'Pong!' to test bot latency."""
        response_content = "Pong!"
        await self.bot.send_message(
            response_content, interaction=ctx.interaction
        )


async def setup(bot):
    await bot.add_cog(Utils(bot))
