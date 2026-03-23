import discord
from discord.ext import commands

from src.core.subscriber import Subscriber


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(name="admin", description="Administrative commands.")
    @commands.has_permissions(administrator=True)
    async def admin(self, ctx: commands.Context):
        """Administrative commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @admin.command(name="refund", description="Refunds score/streak to a player.")
    async def refund(
        self,
        ctx: commands.Context,
        member: discord.Member,
        amount: int,
        streak: int = None,
        *,
        reason: str,
    ):
        """(admin) Refunds score/streak to a player."""
        player_manager = self.bot.player_manager
        player = player_manager.get_or_create_player(
            str(member.id), member.display_name
        )

        player_manager.update_score(str(member.id), amount)

        if streak is not None:
            player_manager.set_streak(str(member.id), streak)

        player = player_manager.get_player(str(member.id))
        if not player:
            await ctx.send(f"Could not find player {member.display_name} after refund.")
            return

        # Log the adjustment using DataManager
        self.bot.data_manager.log_score_adjustment(
            player_id=str(member.id),
            admin_id=str(ctx.author.id),
            amount=amount,
            reason=reason,
        )

        msg = f"Refunded {member.mention}: {amount:+} (Score: {player.score}"
        if streak is not None:
            msg += f", Streak: {streak}"
        msg += f"). Reason: {reason}"

        await ctx.send(msg)

    @admin.command(name="subscribe", description="Sub/unsub from daily questions.")
    async def subscribe(
        self,
        ctx: commands.Context,
        subscribe: bool,
        member: discord.Member = None,
        channel: discord.TextChannel = None,
    ):
        await ctx.defer()
        """(admin) Sub/unsub from daily questions."""
        if not member and not channel:
            await ctx.send("Please provide a member or a channel to subscribe.")
            return

        if member and channel:
            await ctx.send("Please provide either a member or a channel, not both.")
            return

        if member:
            subscriber = Subscriber(
                member.id,
                member.display_name,
                is_channel=False,
            )
            target_name = member.display_name
        else:  # channel
            subscriber = Subscriber(
                channel.id,
                channel.name,
                is_channel=True,
            )
            target_name = channel.name

        if subscribe:
            self.bot.game.add_subscriber(subscriber)
            await ctx.send(f"Subscribed {target_name} to daily questions.")
        else:
            self.bot.game.remove_subscriber(subscriber)
            await ctx.send(f"Unsubscribed {target_name} from daily questions.")
        return

    @admin.command(
        name="add_answer",
        description="(admin) Adds an alternative answer and refunds points.",
    )
    async def add_answer(
        self, ctx: commands.Context, answer_text: str, apply: bool = False
    ):
        # Defer as ephemeral to prevent players from seeing the new answer
        await ctx.interaction.response.defer(ephemeral=True)

        result = self.bot.game.recalculate_scores_for_new_answer(
            answer_text, str(ctx.author.id), dry_run=not apply
        )

        if result["status"] == "error":
            await ctx.interaction.followup.send(f"Error: {result['message']}")
            return

        # Determine if answer has been revealed
        is_revealed = False
        try:
            morning_task = self.bot.morning_message_task
            evening_task = self.bot.evening_message_task
            if morning_task.is_running() and evening_task.is_running():
                if morning_task.next_iteration < evening_task.next_iteration:
                    is_revealed = True
        except Exception:
            pass

        # Build the message body (shared between dry-run and applied)
        if is_revealed:
            header = f"Added ||{answer_text}|| as a correct answer.\n"
        else:
            header = "Added alternative answer.\n"

        summary = (
            f"Updated scores for {result['updated_players']} players.\n"
            f"Total points refunded: {result['total_refunded']}."
        )
        if result.get("age_warning"):
            summary = result["age_warning"] + "\n" + summary

        if apply:
            # Public message only — tag affected players
            public_msg = f"**Score Adjustment:**\n{header}{summary}"
            if result.get("details"):
                public_msg += "\n\n**Details:**\n"
                for d in result["details"]:
                    badges = "".join(d["badges"])
                    public_msg += f"<@{d['user_id']}>: {d['score_before']} -> {d['score_after']} ({d['diff']:+}) {badges}\n"
            if result.get("rest_cleared_players"):
                mentions = " ".join(
                    f"<@{r['user_id']}>" for r in result["rest_cleared_players"]
                )
                public_msg += (
                    f"\nRest revoked — got it right with the new answer: {mentions}"
                )
            await ctx.interaction.followup.send("Done.", ephemeral=True)
            await ctx.channel.send(public_msg)
        else:
            # Ephemeral dry-run message only — no mentions
            dry_msg = f"**[DRY RUN]** No changes applied. Run with `apply=True` to execute.\n{header}{summary}"
            if result.get("details"):
                dry_msg += "\n\n**Details:**\n"
                for d in result["details"]:
                    badges = "".join(d["badges"])
                    dry_msg += f"{d['name']}: {d['score_before']} -> {d['score_after']} ({d['diff']:+}) {badges}\n"
            if result.get("rest_cleared_players"):
                names = ", ".join(r["name"] for r in result["rest_cleared_players"])
                dry_msg += f"\nRest revoked (newly correct with new answer): {names}"
            await ctx.interaction.followup.send(dry_msg)

    @admin.command(name="resend", description="Resend a scheduled message.")
    @discord.app_commands.choices(
        message_type=[
            discord.app_commands.Choice(name="morning", value="morning"),
            discord.app_commands.Choice(name="reminder", value="reminder"),
            discord.app_commands.Choice(name="evening", value="evening"),
        ]
    )
    async def resend(
        self,
        ctx: commands.Context,
        message_type: str,
        silent: bool = True,
        regenerate_hint: bool = False,
    ):
        """(admin) Resend a scheduled message. Optionally regenerate the hint before resending."""
        await ctx.defer()

        # Regenerate hint if requested
        if regenerate_hint:
            if not self.bot.game.daily_q:
                await ctx.send(
                    "Cannot regenerate hint: no active question.", ephemeral=True
                )
                return

            original_hint = self.bot.game.daily_q.hint
            try:
                # Note: This is a blocking call that may take 10+ seconds
                new_hint = self.bot.game.question_selector.get_hint_from_gemini(
                    self.bot.game.daily_q
                )
                if new_hint:
                    self.bot.game.daily_q.hint = new_hint
                    self.bot.data_manager.update_daily_question_hint(
                        self.bot.game.daily_question_id, new_hint
                    )
                    await ctx.send(
                        f"✅ Hint regenerated.\n**Old:** ||{original_hint}||\n**New:** ||{new_hint}||",
                        ephemeral=True,
                    )
                else:
                    await ctx.send(
                        "❌ Hint generation returned empty result.", ephemeral=True
                    )
                    return
            except Exception as e:
                await ctx.send(f"❌ Error generating hint: {e}", ephemeral=True)
                return

        if message_type.lower() == "morning":
            await self.bot.morning_message_task(silent=silent)
            if not silent:
                await ctx.send("Morning message resent.")
        elif message_type.lower() == "reminder":
            await self.bot.reminder_message_task(silent=silent)
            if not silent:
                await ctx.send("Reminder message resent.")
        elif message_type.lower() == "evening":
            await self.bot.evening_message_task(silent=silent)
            if not silent:
                await ctx.send("Evening message resent.")
        else:
            await ctx.send(
                "Invalid message type. Use 'morning', 'reminder', or 'evening'."
            )

        if silent and not regenerate_hint:
            await ctx.send(f"Silently resent {message_type} message.", ephemeral=True)

    @admin.command(name="skip", description="Skips the current daily question.")
    async def skip(self, ctx: commands.Context):
        """(admin) Skips the current daily question."""
        await ctx.defer()

        if not self.bot.game.daily_q:
            await ctx.send("There is no active question to skip.")
            return

        if self.bot.game.reset_daily_question():
            new_question = self.bot.game.daily_q
            question_content = self.bot.game.format_question(new_question)
            await ctx.send(
                f"The daily question has been skipped. The new question is:\n{question_content}"
            )
        else:
            await ctx.send("Failed to skip the daily question. Check the logs.")

    @admin.command(name="ping", description="Check bot response time.")
    async def ping(self, ctx: commands.Context):
        """(admin) Check the bot's response time."""
        response_content = "Pong!"
        await self.bot.send_message(response_content, interaction=ctx.interaction)


async def setup(bot):
    await bot.add_cog(Admin(bot))
