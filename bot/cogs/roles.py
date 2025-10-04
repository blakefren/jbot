# bot/cogs/roles.py
import discord
from discord.ext import commands, tasks
from bot.modes.roles import RolesGameMode
from database.database import Database


class RolesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.roles_game_mode = RolesGameMode(self.db, self.bot.config)
        if self.bot.config.get_bool("ENABLE_ROLES"):
            self.update_roles_task.start()

    def cog_unload(self):
        self.update_roles_task.cancel()

    @commands.hybrid_command(
        name="updateroles", help="Manually update player roles based on scores."
    )
    @commands.has_permissions(administrator=True)
    async def update_roles(self, ctx):
        await ctx.send("Updating roles...")
        self.roles_game_mode.run()
        await self.apply_discord_roles(ctx.guild)
        await ctx.send("Roles updated.")

    @tasks.loop(hours=1)  # Or some other interval
    async def update_roles_task(self):
        # This will run periodically to update roles automatically
        # Find a guild to run this on. This is a bit of a hack.
        # A better solution would be to store guild_id in config.
        for guild in self.bot.guilds:
            self.roles_game_mode.run()
            await self.apply_discord_roles(guild)

    async def apply_discord_roles(self, guild: discord.Guild):
        with self.db.get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT pr.player_id, r.name 
                FROM player_roles pr
                JOIN roles r ON pr.role_id = r.id
            """
            )
            player_roles_from_db = cursor.fetchall()

        # Get all members from the guild
        members = {str(m.id): m for m in guild.members}

        # Get all roles from the guild
        guild_roles = {r.name: r for r in guild.roles}

        # Clear all managed roles first
        # TODO: read config from other file
        managed_role_names = [
            "First Place",
            "Top 10%",
        ]  # Add any other roles you manage
        for role_name in managed_role_names:
            if role_name in guild_roles:
                role_to_clear = guild_roles[role_name]
                for member in role_to_clear.members:
                    await member.remove_roles(role_to_clear)

        # Assign roles
        for player_id, role_name in player_roles_from_db:
            if player_id in members:
                member = members[player_id]
                role = guild_roles.get(role_name)
                if not role:
                    # Create the role if it doesn't exist
                    role = await guild.create_role(
                        name=role_name, reason="JBot role management"
                    )
                    guild_roles[role_name] = role

                if role not in member.roles:
                    await member.add_roles(role)


async def setup(bot):
    await bot.add_cog(RolesCog(bot))
