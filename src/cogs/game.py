import discord
from discord.ext import commands
from datetime import datetime


class Game(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(name="game", description="Game information and status.")
    async def game(self, ctx: commands.Context):
        """Game information and status."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @game.command(name="status", description="Show current game status and next event.")
    async def status(self, ctx: commands.Context):
        """Next event time & current question."""
        morning_task = self.bot.morning_message_task
        evening_task = self.bot.evening_message_task

        if not morning_task.is_running() or not evening_task.is_running():
            await self.bot.send_message(
                "Tasks are not running.", interaction=ctx.interaction, ephemeral=True
            )
            return

        morning_time_next = morning_task.next_iteration
        evening_time_next = evening_task.next_iteration

        if morning_time_next < evening_time_next:
            event_name = "next question"
            next_datetime = morning_time_next
        else:
            event_name = "answer reveal"
            next_datetime = evening_time_next

        response_content = (
            f"The {event_name} is <t:{int(next_datetime.timestamp())}:R> "
            f"(at <t:{int(next_datetime.timestamp())}:T>)."
        )

        # If there's an active question, show it.
        if self.bot.game.daily_q and morning_time_next > evening_time_next:
            response_content += (
                "\n\n**Today's Question:**\n"
                + self.bot.game.format_question(self.bot.game.daily_q)
            )

        # Add player summary
        player_id = ctx.author.id
        player = self.bot.player_manager.get_player(str(player_id))
        if player:
            response_content += f"\n\n**Your Score:** {player.score} | **Streak:** {player.answer_streak}"

        await self.bot.send_message(
            response_content, interaction=ctx.interaction, ephemeral=True
        )

    @game.command(name="leaderboard", description="View the current leaderboard.")
    async def leaderboard(
        self, ctx: commands.Context, show_daily_bonuses: bool = False
    ):
        """View the current score leaderboard."""
        leaderboard = self.bot.game.get_scores_leaderboard(
            ctx.guild, show_daily_bonuses=show_daily_bonuses
        )
        await self.bot.send_message(leaderboard, interaction=ctx.interaction)

    @game.command(name="profile", description="View your player profile.")
    async def profile(self, ctx: commands.Context):
        """View your game history and stats."""
        player_id = ctx.author.id
        player_name = ctx.author.display_name
        history_text = self.bot.game.get_player_history(player_id, player_name)
        await self.bot.send_message(
            history_text, interaction=ctx.interaction, ephemeral=True
        )

    @game.command(name="rules", description="Show active game rules.")
    async def rules(self, ctx: commands.Context):
        """Show active game rules."""
        features = self.bot.game.features
        rules_text = "**Active Game Rules:**\n"

        if features.get("fight"):
            rules_text += "- **Fight Track**: PvP enabled! Use `/power disrupt` to attack streaks and `/power steal` to steal points.\n"
        if features.get("powerup"):
            rules_text += "- **Power-up Track**: Power-ups enabled! Use `/power wager` to bet points.\n"
        if features.get("coop"):
            rules_text += "- **Coop Track**: Cooperation enabled! Use `/power reinforce` to team up.\n"

        if not any(features.values()):
            rules_text += "Standard trivia rules apply. Answer daily questions to earn points and streaks!"

        await self.bot.send_message(
            rules_text, interaction=ctx.interaction, ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Game(bot))
