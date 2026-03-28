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
        reminder_task = self.bot.reminder_message_task
        evening_task = self.bot.evening_message_task

        if (
            not morning_task.is_running()
            or not reminder_task.is_running()
            or not evening_task.is_running()
        ):
            await self.bot.send_message(
                "Tasks are not running.", interaction=ctx.interaction, ephemeral=True
            )
            return

        morning_time_next = morning_task.next_iteration
        reminder_time_next = reminder_task.next_iteration
        evening_time_next = evening_task.next_iteration

        # Determine the next event by finding the earliest time
        events = [
            ("Next question", morning_time_next),
            ("Reminder", reminder_time_next),
            ("Answer reveal", evening_time_next),
        ]
        event_name, next_datetime = min(events, key=lambda x: x[1])

        response_content = (
            f"{event_name} in <t:{int(next_datetime.timestamp())}:R> "
            f"(<t:{int(next_datetime.timestamp())}:T>)."
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
        self,
        ctx: commands.Context,
        show_daily_bonuses: bool = False,
        all_time: bool = False,
    ):
        """View the current score leaderboard."""
        game = self.bot.game
        season_manager = game.season_manager

        if season_manager.enabled:
            if all_time:
                entries = season_manager.get_all_time_leaderboard()
                if not entries:
                    await self.bot.send_message(
                        "No scores yet.", interaction=ctx.interaction
                    )
                    return
                lines = ["**-- All-Time Leaderboard --**\n```"]
                for i, (player_dict, player_name) in enumerate(entries, start=1):
                    score = player_dict["score"]
                    counts = game.data_manager.get_trophy_counts(
                        player_dict["player_id"]
                    )
                    trophy_parts = []
                    if counts.get("gold"):
                        trophy_parts.append(f"🥇×{counts['gold']}")
                    if counts.get("silver"):
                        trophy_parts.append(f"🥈×{counts['silver']}")
                    if counts.get("bronze"):
                        trophy_parts.append(f"🥉×{counts['bronze']}")
                    trophy_str = " " + " ".join(trophy_parts) if trophy_parts else ""
                    lines.append(
                        f"{i:>2}. {player_name:<16} {score:>7} pts{trophy_str}"
                    )
                lines.append("```")
                await self.bot.send_message(
                    "\n".join(lines), interaction=ctx.interaction
                )
            else:
                current_season = game.data_manager.get_current_season()
                if not current_season:
                    lb = game.get_scores_leaderboard(
                        ctx.guild, show_daily_bonuses=show_daily_bonuses
                    )
                    await self.bot.send_message(lb, interaction=ctx.interaction)
                    return
                current_day, total_days = season_manager.get_season_progress(
                    current_season
                )
                entries = season_manager.get_season_leaderboard(
                    current_season.season_id
                )
                emoji_streak = game.config.get("JBOT_EMOJI_STREAK")
                header = f"**-- {current_season.season_name} (Day {current_day}/{total_days}) --**"
                if not entries:
                    await self.bot.send_message(
                        f"{header}\nNo scores this season yet.",
                        interaction=ctx.interaction,
                    )
                    return
                lines = [header + "\n```"]
                for i, (score, player_name) in enumerate(entries, start=1):
                    streak_str = (
                        f" {emoji_streak}{score.current_streak}"
                        if score.current_streak >= 2
                        else ""
                    )
                    lines.append(
                        f"{i:>2}. {player_name:<16} {score.points:>6} pts{streak_str}"
                    )
                lines.append("```")
                await self.bot.send_message(
                    "\n".join(lines), interaction=ctx.interaction
                )
        else:
            lb = game.get_scores_leaderboard(
                ctx.guild, show_daily_bonuses=show_daily_bonuses
            )
            await self.bot.send_message(lb, interaction=ctx.interaction)

    @game.command(name="profile", description="View your player profile.")
    async def profile(self, ctx: commands.Context, all_time: bool = False):
        """View your game history and stats."""
        player_id = ctx.author.id
        player_name = ctx.author.display_name
        game = self.bot.game
        season_manager = game.season_manager

        if season_manager.enabled and not all_time:
            current_season = game.data_manager.get_current_season()
            if current_season:
                season_score = game.data_manager.get_player_season_score(
                    str(player_id), current_season.season_id
                )
                if season_score:
                    correct_rate = (
                        (season_score.correct_answers / season_score.questions_answered)
                        * 100
                        if season_score.questions_answered > 0
                        else 0
                    )
                    lines = [
                        f"-- {current_season.season_name}, {player_name} --",
                        f"Season Score:  {season_score.points}",
                        f"Streak:        {season_score.current_streak} day(s) (best: {season_score.best_streak})",
                        f"Correct:       {season_score.correct_answers}/{season_score.questions_answered} ({correct_rate:.1f}%)",
                    ]
                    history_text = "\n".join(lines)
                else:
                    history_text = (
                        f"No season stats yet for {player_name} this season. "
                        "Answer today's question to get started!"
                    )
                await self.bot.send_message(
                    history_text, interaction=ctx.interaction, ephemeral=True
                )
                return

        history_text = game.get_player_history(player_id, player_name)
        await self.bot.send_message(
            history_text, interaction=ctx.interaction, ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Game(bot))
