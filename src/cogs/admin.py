import discord
from discord.ext import commands

from cfg.players import PlayerManager
from core.subscriber import Subscriber
from src.cfg.players import read_players_into_dict

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command()
    @commands.is_owner()
    async def sync(self, ctx: commands.Context):
        """Syncs the command tree."""
        # TODO: error when running this command:
        # An unexpected error occurred in command 'sync':
        # Hybrid command raised an error:
        # Command 'sync' raised an exception:
        # NotFound: 404 Not Found (error code: 10062):
        # Unknown interaction
        await self.bot.tree.sync()
        await ctx.send("Command tree synced.")

    @commands.hybrid_command()
    @commands.is_owner()
    async def refund(self, ctx: commands.Context, member: discord.Member, amount: int, *, reason: str):
        """Refunds score to a player."""
        player_manager = PlayerManager(self.bot.data_manager.db)
        player = player_manager.get_player(str(member.id))

        if not player:
            # Create a new player if they don't exist
            player_manager.players[str(member.id)] = {
                "name": member.display_name,
                "score": 0,
                "answer_streak": 0,
                "active_shield": False,
            }
            player = player_manager.get_player(str(member.id))

        player["score"] += amount
        self.bot.game.update_scores()

        # Log the adjustment
        # TODO: Migrate this to a DataManager method
        self.bot.data_manager.db.execute_update(
            "INSERT INTO score_adjustments (player_id, admin_id, amount, reason) VALUES (?, ?, ?, ?)",
            (str(member.id), str(ctx.author.id), amount, reason),
        )

        await ctx.send(f"Refunded {amount} to {member.display_name}. New score: {player['score']}. Reason: {reason}")

    @commands.hybrid_command()
    @commands.is_owner()
    async def subscribe(
        self,
        ctx: commands.Context,
        subscribe: bool,
        member: discord.Member = None,
        channel: discord.TextChannel = None,
    ):
        await ctx.defer()
        """Sub/unsub a user/channel from daily questions."""
        if not member and not channel:
            await ctx.send("Please provide a member or a channel to subscribe.")
            return

        if member and channel:
            await ctx.send("Please provide either a member or a channel, not both.")
            return

        if member:
            subscriber = Subscriber(
                member.id, member.display_name, is_channel=False, db_conn=self.bot.data_manager.db
            )
            target_name = member.display_name
        else:  # channel
            subscriber = Subscriber(
                channel.id, channel.name, is_channel=True, db_conn=self.bot.data_manager.db
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
    @commands.is_owner()
    @discord.app_commands.choices(
        message_type=[
            discord.app_commands.Choice(name="morning", value="morning"),
            discord.app_commands.Choice(name="reminder", value="reminder"),
            discord.app_commands.Choice(name="evening", value="evening"),
        ]
    )
    async def resend(self, ctx: commands.Context, message_type: str):
        """Resend a scheduled message."""
        if message_type.lower() == "morning":
            await self.bot.morning_message_task()
            await ctx.send("Morning message resent.")
        elif message_type.lower() == "reminder":
            await self.bot.reminder_message_task()
            await ctx.send("Reminder message resent.")
        elif message_type.lower() == "evening":
            await self.bot.evening_message_task()
            await ctx.send("Evening message resent.")
        else:
            await ctx.send("Invalid message type. Use 'morning', 'reminder', or 'evening'.")

    @commands.hybrid_group(name="feature", description="Manage game features.")
    @commands.is_owner()
    async def feature(self, ctx: commands.Context):
        """A group of commands to manage game features."""
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
        """Enables a game feature by name."""
        # You might need to pass arguments to the manager's constructor
        kwargs = {}
        if feature_name == "powerup":
            kwargs['players'] = [k for k in read_players_into_dict().keys()]
        elif feature_name == "roles":
            kwargs['db'] = self.bot.data_manager.db
            from cfg.main import ConfigReader
            kwargs['config'] = ConfigReader()

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
        """Disables a game feature by name."""
        self.bot.game.disable_manager(feature_name)
        await ctx.send(f"Feature '{feature_name}' disabled.")

async def setup(bot):
    await bot.add_cog(Admin(bot))
