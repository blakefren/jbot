import discord
from discord.ext import commands

from cfg.players import PlayerManager
from bot.subscriber import Subscriber

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command()
    @commands.is_owner()
    async def sync(self, ctx: commands.Context):
        """Syncs the command tree."""
        await self.bot.tree.sync()
        await ctx.send("Command tree synced.")

    @commands.hybrid_command()
    @commands.is_owner()
    async def refund(self, ctx: commands.Context, member: discord.Member, amount: int, *, reason: str):
        """Refunds a player a certain amount of score."""
        player_manager = PlayerManager(self.bot.logger.db)
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
        player_manager.save_players()

        # Log the adjustment
        self.bot.logger.db.execute_update(
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
        """Subscribes or unsubscribes a user or channel from daily questions."""
        if not member and not channel:
            await ctx.send("Please provide a member or a channel to subscribe.")
            return

        if member and channel:
            await ctx.send("Please provide either a member or a channel, not both.")
            return

        if member:
            subscriber = Subscriber(
                member.id, member.display_name, is_channel=False, db_conn=self.bot.logger.db
            )
            target_name = member.display_name
        else:  # channel
            subscriber = Subscriber(
                channel.id, channel.name, is_channel=True, db_conn=self.bot.logger.db
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
    async def resend(self, ctx: commands.Context, message_type: str):
        """Resends a scheduled message (morning, reminder, or evening)."""
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

async def setup(bot):
    await bot.add_cog(Admin(bot))
