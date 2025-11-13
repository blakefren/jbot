# bot/cogs/roles.py
import discord
from discord.ext import commands, tasks
from src.core.roles import RolesGameMode

import sys
import os

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)


class RolesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.roles_game_mode = RolesGameMode(self.bot.data_manager, self.bot.config)

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    async def update_roles(self, ctx):
        """(admin) Manually update player roles."""
        await ctx.send("Updating roles...")
        self.roles_game_mode.run()
        await self.apply_discord_roles(ctx.guild)
        await ctx.send("Roles updated.")

    async def apply_discord_roles(self, guild: discord.Guild):
        """
        Efficiently applies the 'first place' role to the current winner(s).
        - Fetches the role name from config.
        - Determines who should have the role from the database.
        - Compares against who currently has the role in Discord.
        - Only adds or removes roles if there is a change.
        """
        first_place_role_name = self.bot.config.get("JBOT_FIRST_PLACE_ROLE_NAME")
        if not first_place_role_name:
            return  # Or log a warning

        # Get the discord.Role object, creating it if it doesn't exist.
        role = discord.utils.get(guild.roles, name=first_place_role_name)
        if not role:
            try:
                role = await guild.create_role(
                    name=first_place_role_name, reason="JBot: Create First Place Role",
                )
            except discord.Forbidden:
                # Log that we don't have permissions to create roles
                return

        # Get the set of player IDs that should have the role from the database
        db_winners = self.bot.data_manager.get_player_ids_with_role(
            first_place_role_name
        )

        # Get the set of members who currently have the role in Discord
        discord_winners = {member.id for member in role.members}

        # Determine who to add and who to remove
        to_add = db_winners - discord_winners
        to_remove = discord_winners - db_winners

        # Add the role to new winners
        for member_id in to_add:
            member = guild.get_member(member_id)
            if member:
                await member.add_roles(role, reason="JBot: Player achieved first place")

        # Remove the role from previous winners
        for member_id in to_remove:
            member = guild.get_member(member_id)
            if member:
                await member.remove_roles(
                    role, reason="JBot: Player no longer in first place"
                )


async def setup(bot):
    await bot.add_cog(RolesCog(bot))
