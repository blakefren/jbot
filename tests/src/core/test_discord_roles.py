import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import os

# Add the project root to the Python path
project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
sys.path.insert(0, project_root)

import discord
from db.database import Database
from src.core.data_manager import DataManager
from src.core.discord import DiscordBot


class TestDiscordRoles(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.data_manager = DataManager(self.db)

    def tearDown(self):
        self.db.close()

    def _seed_winner(self, player_id):
        # The DB stores player IDs as TEXT, while Discord uses int IDs
        self.data_manager.create_player(player_id, f"Player{player_id}")
        self.data_manager.assign_role_to_player(player_id, "First Place")

    async def test_apply_discord_roles_type_mismatch_fix(self):
        """Test that string IDs from DB are converted to ints for Discord."""
        # Setup mocks
        bot = MagicMock(spec=DiscordBot)
        bot.config = MagicMock()
        bot.data_manager = self.data_manager
        # Bind the real method to the mock object
        bot.apply_discord_roles = DiscordBot.apply_discord_roles.__get__(
            bot, DiscordBot
        )

        # Config
        bot.config.get.return_value = "First Place"

        # Mock Guild and Role
        guild = MagicMock(spec=discord.Guild)
        role = MagicMock(spec=discord.Role)
        role.name = "First Place"
        role.members = []  # Initially empty, so discord_winners = set()

        # Guild.roles
        guild.roles = [role]

        # Member mock
        member_mock = MagicMock(spec=discord.Member)
        member_mock.id = 12345
        member_mock.display_name = "TestUser"
        member_mock.add_roles = AsyncMock()

        # Guild.get_member
        # Crucial: Check if it receives INT. If str, verify failure (or just assert call args later)
        def get_member_mock(user_id):
            if user_id == 12345:  # Matching int
                return member_mock
            return None

        guild.get_member.side_effect = get_member_mock
        guild.fetch_member = AsyncMock()

        self._seed_winner("12345")

        # Run method
        await bot.apply_discord_roles(guild)

        # Assertions
        # 1. get_member called with INT 12345.
        # If passing string "12345", the side_effect logic might fail or strict mock comparison would show string.
        guild.get_member.assert_called_with(12345)

        # 2. Member.add_roles called
        member_mock.add_roles.assert_called_once()

        # 3. Fetch not called because get_member succeeded
        guild.fetch_member.assert_not_called()

    async def test_apply_discord_roles_fetch_fallback(self):
        """Test fallback to fetch_member if get_member returns None."""
        bot = MagicMock(spec=DiscordBot)
        bot.config = MagicMock()
        bot.data_manager = self.data_manager
        bot.apply_discord_roles = DiscordBot.apply_discord_roles.__get__(
            bot, DiscordBot
        )

        bot.config.get.return_value = "First Place"

        guild = MagicMock(spec=discord.Guild)
        role = MagicMock(spec=discord.Role)
        role.name = "First Place"
        role.members = []
        guild.roles = [role]

        # get_member always returns None (cache miss)
        guild.get_member.return_value = None

        # fetch_member returns member
        member_mock = MagicMock(spec=discord.Member)
        member_mock.id = 999
        member_mock.display_name = "FetchedUser"
        member_mock.add_roles = AsyncMock()
        guild.fetch_member.return_value = member_mock

        self._seed_winner("999")

        await bot.apply_discord_roles(guild)

        guild.get_member.assert_called_with(999)
        guild.fetch_member.assert_called_with(999)
        member_mock.add_roles.assert_called_once()
