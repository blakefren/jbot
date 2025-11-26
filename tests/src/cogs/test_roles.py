# tests/src/cogs/test_roles.py
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import discord

import sys
import os

# Add the project root to the Python path
project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
sys.path.insert(0, project_root)

from src.cogs.roles import RolesCog


class TestRolesCog(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Mock Bot
        self.bot = MagicMock()
        self.bot.config = MagicMock()
        self.bot.config.get.return_value = "first place"
        self.bot.data_manager = MagicMock()
        self.bot.data_manager.get_player_ids_with_role = MagicMock()

        # Mock Guild and Members
        self.guild = MagicMock(spec=discord.Guild)
        self.member1 = self._create_mock_member(101)  # New winner
        self.member2 = self._create_mock_member(102)  # Existing winner
        self.member3 = self._create_mock_member(103)  # To be removed

        self.guild.get_member.side_effect = lambda mid: {
            101: self.member1,
            102: self.member2,
            103: self.member3,
        }.get(mid)

        # Mock Role
        self.first_place_role = MagicMock(spec=discord.Role)
        self.first_place_role.name = "first place"
        self.first_place_role.members = [self.member2, self.member3]
        self.guild.roles = [self.first_place_role]

        # Create Cog instance
        self.cog = RolesCog(self.bot)

    def _create_mock_member(self, member_id):
        member = MagicMock(spec=discord.Member)
        member.id = member_id
        member.add_roles = AsyncMock()
        member.remove_roles = AsyncMock()
        return member

    @patch("discord.utils.get")
    async def test_apply_roles_add_and_remove(self, mock_utils_get):
        """Test that roles are added to new winners and removed from old ones."""
        mock_utils_get.return_value = self.first_place_role

        # DB winners: member1 and member2
        self.bot.data_manager.get_player_ids_with_role.return_value = {101, 102}

        await self.cog.apply_discord_roles(self.guild)

        # member1 should get the role
        self.member1.add_roles.assert_awaited_once_with(
            self.first_place_role, reason="JBot: Player achieved first place"
        )
        # member3 should lose the role
        self.member3.remove_roles.assert_awaited_once_with(
            self.first_place_role, reason="JBot: Player no longer in first place"
        )
        # member2 is already a winner, so no calls should be made
        self.member2.add_roles.assert_not_awaited()
        self.member2.remove_roles.assert_not_awaited()

    @patch("discord.utils.get")
    async def test_apply_roles_no_change(self, mock_utils_get):
        """Test that no roles are changed if the winner is the same."""
        mock_utils_get.return_value = self.first_place_role
        self.first_place_role.members = [self.member1]

        # DB winner: member1
        self.bot.data_manager.get_player_ids_with_role.return_value = {101}

        await self.cog.apply_discord_roles(self.guild)

        # No calls should be made
        self.member1.add_roles.assert_not_awaited()
        self.member1.remove_roles.assert_not_awaited()

    @patch("discord.utils.get")
    async def test_role_creation(self, mock_utils_get):
        """Test that the role is created if it doesn't exist."""
        mock_utils_get.return_value = None  # Role does not exist
        self.guild.create_role = AsyncMock(return_value=self.first_place_role)

        # DB winner: member1
        self.bot.data_manager.get_player_ids_with_role.return_value = {101}
        self.first_place_role.members = []  # No one has the role yet

        await self.cog.apply_discord_roles(self.guild)

        # Verify role was created
        self.guild.create_role.assert_awaited_once_with(
            name="first place", reason="JBot: Create First Place Role"
        )
        # Verify role was added to the new winner
        self.member1.add_roles.assert_awaited_once_with(
            self.first_place_role, reason="JBot: Player achieved first place"
        )

    @patch("discord.utils.get")
    async def test_role_creation_forbidden(self, mock_utils_get):
        """Test that the function returns gracefully when role creation is forbidden."""
        mock_utils_get.return_value = None  # Role does not exist
        self.guild.create_role = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "Missing permissions")
        )

        # DB winner: member1
        self.bot.data_manager.get_player_ids_with_role.return_value = {101}

        # Should not raise an exception
        await self.cog.apply_discord_roles(self.guild)

        # Verify role creation was attempted
        self.guild.create_role.assert_awaited_once()
        # Verify no role assignments were made
        self.member1.add_roles.assert_not_awaited()

    @patch("discord.utils.get")
    async def test_no_role_name_configured(self, mock_utils_get):
        """Test that the function returns early when no role name is configured."""
        self.bot.config.get.return_value = None  # No role name configured

        await self.cog.apply_discord_roles(self.guild)

        # Verify discord.utils.get was not called
        mock_utils_get.assert_not_called()
        # Verify no data_manager calls were made
        self.bot.data_manager.get_player_ids_with_role.assert_not_called()

    @patch("discord.utils.get")
    async def test_apply_roles_member_not_in_guild(self, mock_utils_get):
        """Test that missing members are handled gracefully."""
        mock_utils_get.return_value = self.first_place_role
        self.first_place_role.members = []

        # DB winner: member 999 who is not in the guild
        self.bot.data_manager.get_player_ids_with_role.return_value = {999}
        self.guild.get_member.side_effect = lambda mid: None  # No members found

        # Should not raise an exception
        await self.cog.apply_discord_roles(self.guild)

        # Verify no role assignments were made (member not found)
        self.member1.add_roles.assert_not_awaited()

    async def test_update_roles_command(self):
        """Test the update_roles command."""
        ctx = MagicMock()
        ctx.send = AsyncMock()
        ctx.guild = self.guild

        # Mock the roles_game_mode.run() method
        self.cog.roles_game_mode = MagicMock()
        self.cog.roles_game_mode.run = MagicMock()

        # Mock apply_discord_roles
        self.cog.apply_discord_roles = AsyncMock()

        await self.cog.update_roles.callback(self.cog, ctx)

        # Verify the flow
        ctx.send.assert_any_call("Updating roles...")
        self.cog.roles_game_mode.run.assert_called_once()
        self.cog.apply_discord_roles.assert_awaited_once_with(self.guild)
        ctx.send.assert_any_call("Roles updated.")


class TestRolesCogSetup(unittest.IsolatedAsyncioTestCase):
    async def test_setup(self):
        """Test that the setup function adds the cog."""
        from src.cogs.roles import setup

        mock_bot = MagicMock()
        mock_bot.add_cog = AsyncMock()
        mock_bot.config = MagicMock()
        mock_bot.data_manager = MagicMock()

        await setup(mock_bot)

        mock_bot.add_cog.assert_called_once()
        call_args = mock_bot.add_cog.call_args
        self.assertIsInstance(call_args[0][0], RolesCog)


if __name__ == "__main__":
    unittest.main()
