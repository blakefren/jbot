import discord
from discord.ext import commands

from src.core.subscriber import Subscriber


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command()
    @commands.is_owner()
    async def sync(self, ctx: commands.Context):
        """(owner) Syncs the command tree."""
        # TODO: error when running this command:
        # An unexpected error occurred in command 'sync':
        # Hybrid command raised an error:
        # Command 'sync' raised an exception:
        # NotFound: 404 Not Found (error code: 10062):
        # Unknown interaction
        await self.bot.tree.sync()
        await ctx.send("Command tree synced.")

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
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

        player_manager.refund_score(str(member.id), amount)

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

        msg = f"Refunded {amount} to {member.display_name}. New score: {player.score}."
        if streak is not None:
            msg += f" Streak set to {streak}."
        msg += f" Reason: {reason}"

        await ctx.send(msg)

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
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
                db_conn=self.bot.data_manager.db,
            )
            target_name = member.display_name
        else:  # channel
            subscriber = Subscriber(
                channel.id,
                channel.name,
                is_channel=True,
                db_conn=self.bot.data_manager.db,
            )
            target_name = channel.name

        if subscribe:
            self.bot.game.add_subscriber(subscriber)
            await ctx.send(f"Subscribed {target_name} to daily questions.")
        else:
            self.bot.game.remove_subscriber(subscriber)
            await ctx.send(f"Unsubscribed {target_name} from daily questions.")
        return

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    @discord.app_commands.choices(
        message_type=[
            discord.app_commands.Choice(name="morning", value="morning"),
            discord.app_commands.Choice(name="reminder", value="reminder"),
            discord.app_commands.Choice(name="evening", value="evening"),
        ]
    )
    async def resend(
        self, ctx: commands.Context, message_type: str, silent: bool = True
    ):
        """(admin) Resend a scheduled message."""
        await ctx.defer()
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

        if silent:
            await ctx.send(f"Silently resent {message_type} message.", ephemeral=True)

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
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

    @commands.hybrid_group(name="feature", description="Manage game features.")
    @commands.is_owner()
    async def feature(self, ctx: commands.Context):
        """(owner) Manage game features."""
        if ctx.invoked_subcommand is None:
            await ctx.send("Invalid feature command. Use `enable` or `disable`.")

    @feature.command(name="enable", description="Enable a game feature.")
    @discord.app_commands.choices(
        feature_name=[
            discord.app_commands.Choice(name="fight", value="fight"),
            discord.app_commands.Choice(name="powerup", value="powerup"),
            discord.app_commands.Choice(name="coop", value="coop"),
            discord.app_commands.Choice(name="roles", value="roles"),
        ]
    )
    async def enable_feature(self, ctx: commands.Context, feature_name: str):
        """(owner) Enable a game feature."""
        # You might need to pass arguments to the manager's constructor
        kwargs = {}
        if feature_name == "powerup":
            kwargs["players"] = [
                k for k in self.bot.player_manager.get_all_players().keys()
            ]
        elif feature_name == "roles":
            kwargs["db"] = self.bot.data_manager.db
            from src.cfg.main import ConfigReader

            kwargs["config"] = ConfigReader()

        self.bot.game.enable_manager(feature_name, **kwargs)
        await ctx.send(f"Feature '{feature_name}' enabled.")

    @feature.command(name="disable", description="Disable a game feature.")
    @discord.app_commands.choices(
        feature_name=[
            discord.app_commands.Choice(name="fight", value="fight"),
            discord.app_commands.Choice(name="powerup", value="powerup"),
            discord.app_commands.Choice(name="coop", value="coop"),
            discord.app_commands.Choice(name="roles", value="roles"),
        ]
    )
    async def disable_feature(self, ctx: commands.Context, feature_name: str):
        """(owner) Disable a game feature."""
        self.bot.game.disable_manager(feature_name)
        await ctx.send(f"Feature '{feature_name}' disabled.")


async def setup(bot):
    await bot.add_cog(Admin(bot))
