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
        self.bot.config.get_string.return_value = "first place"
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


if __name__ == "__main__":
    unittest.main()
