import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.cogs.game import Game
from tests.src.cogs._game_stack import build_game_stack


class TestGameCog(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._make_cog(build_game_stack(self, players=(("123", "Test"),)))
        self.ctx = AsyncMock()
        self.ctx.interaction = MagicMock()
        self.ctx.guild = None
        self.ctx.author.id = 123
        self.ctx.author.display_name = "Test"

    def _make_cog(self, stack):
        self.stack = stack
        self.bot = SimpleNamespace(
            game=stack.game,
            player_manager=stack.player_manager,
            # Scheduler tasks are discord.ext.tasks loops, so they stay doubles.
            morning_message_task=MagicMock(),
            reminder_message_task=MagicMock(),
            evening_message_task=MagicMock(),
            send_message=AsyncMock(),
        )
        self.cog = Game(self.bot)

    def _schedule(self, morning, reminder, evening):
        for task, next_iteration in (
            (self.bot.morning_message_task, morning),
            (self.bot.reminder_message_task, reminder),
            (self.bot.evening_message_task, evening),
        ):
            task.is_running.return_value = True
            task.next_iteration = next_iteration

    def _sent_text(self):
        self.bot.send_message.assert_awaited_once()
        return self.bot.send_message.await_args.args[0]

    async def test_status_tasks_not_running(self):
        self.bot.morning_message_task.is_running.return_value = False
        await self.cog.status.callback(self.cog, self.ctx)
        self.assertIn("Tasks are not running", self._sent_text())

    async def test_status_next_question(self):
        self._schedule(
            datetime(2025, 1, 1, 8, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 1, 14, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 1, 20, 0, tzinfo=timezone.utc),
        )

        await self.cog.status.callback(self.cog, self.ctx)

        text = self._sent_text()
        self.assertIn("Next question", text)
        self.assertNotIn("Today's Question:", text)

    async def test_status_answer_reveal(self):
        """Test status when it's time for answer reveal (evening < morning)."""
        self._make_cog(build_game_stack(self, start_day=False))
        self._schedule(
            datetime(2025, 1, 2, 8, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 2, 14, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 1, 20, 0, tzinfo=timezone.utc),
        )

        await self.cog.status.callback(self.cog, self.ctx)

        self.assertIn("Answer reveal", self._sent_text())

    async def test_status_with_active_question(self):
        """Test status showing the active question."""
        self._schedule(
            datetime(2025, 1, 2, 8, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 2, 14, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 1, 20, 0, tzinfo=timezone.utc),
        )

        await self.cog.status.callback(self.cog, self.ctx)

        text = self._sent_text()
        self.assertIn("Today's Question:", text)
        self.assertIn("What is 2 + 2?", text)

    async def test_status_with_player_stats(self):
        """Test status showing player stats."""
        self.stack.player_manager.update_score("123", 100)
        self.stack.player_manager.set_streak("123", 5)
        self._schedule(
            datetime(2025, 1, 1, 8, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 1, 14, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 1, 20, 0, tzinfo=timezone.utc),
        )

        await self.cog.status.callback(self.cog, self.ctx)

        text = self._sent_text()
        self.assertIn("**Your Score:** 100", text)
        self.assertIn("**Streak:** 5", text)

    async def test_status_player_not_found(self):
        """Test status when player is not found."""
        self.ctx.author.id = 999
        self._schedule(
            datetime(2025, 1, 1, 8, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 1, 14, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 1, 20, 0, tzinfo=timezone.utc),
        )

        await self.cog.status.callback(self.cog, self.ctx)

        self.assertNotIn("**Your Score:**", self._sent_text())

    async def test_status_reminder_next(self):
        """Test status when reminder is the next event."""
        self._make_cog(build_game_stack(self, start_day=False))
        self._schedule(
            datetime(2025, 1, 2, 8, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 1, 14, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 1, 20, 0, tzinfo=timezone.utc),
        )

        await self.cog.status.callback(self.cog, self.ctx)

        self.assertIn("Reminder", self._sent_text())

    def _seed_scores(self):
        player_manager = self.stack.player_manager
        for player_id, name, score in (("p1", "Alice", 70), ("p2", "Bob", 90)):
            player_manager.get_or_create_player(player_id, name)
            player_manager.update_score(player_id, score)
            # The all-time leaderboard only lists recently active players.
            self.stack.data_manager.log_player_guess(
                player_id, name, self.stack.game.daily_question_id, "x", False
            )

    def _seed_season(self):
        today = date.today()
        season_id = self.stack.data_manager.create_season(
            "Test Season",
            (today - timedelta(days=2)).isoformat(),
            (today + timedelta(days=27)).isoformat(),
        )
        for player_id, points in (("p1", 30), ("p2", 50)):
            self.stack.data_manager.initialize_player_season_score(player_id, season_id)
            self.stack.data_manager.update_season_score(
                player_id, season_id, points=points
            )
        return season_id

    async def test_leaderboard_seasons_disabled(self):
        self._seed_scores()

        await self.cog.leaderboard.callback(self.cog, self.ctx)

        text = self._sent_text()
        self.assertLess(text.index("Bob"), text.index("Alice"))
        self.assertIn("90", text)
        self.assertNotIn("Season", text)
        self.assertIs(
            self.bot.send_message.await_args.kwargs["interaction"],
            self.ctx.interaction,
        )

    async def test_leaderboard_seasons_enabled_shows_season(self):
        self._make_cog(
            build_game_stack(
                self, players=(("p1", "Alice"), ("p2", "Bob")), seasons=True
            )
        )
        self._seed_season()

        await self.cog.leaderboard.callback(self.cog, self.ctx)

        text = self._sent_text()
        self.assertIn("Test Season", text)
        self.assertIn("Alice", text)
        self.assertLess(text.index("Bob"), text.index("Alice"))
        self.assertNotIn("All-Time", text)

    async def test_leaderboard_seasons_enabled_no_season_falls_back(self):
        stack = build_game_stack(
            self,
            players=(("p1", "Alice"), ("p2", "Bob")),
            seasons=True,
            season_auto_create=False,
        )
        self._make_cog(stack)
        self._seed_scores()

        await self.cog.leaderboard.callback(self.cog, self.ctx)

        text = self._sent_text()
        self.assertIn("Bob", text)
        self.assertNotIn("Season", text)

    async def test_leaderboard_seasons_enabled_all_time_flag(self):
        self._make_cog(
            build_game_stack(
                self, players=(("p1", "Alice"), ("p2", "Bob")), seasons=True
            )
        )
        self._seed_season()
        self._seed_scores()

        await self.cog.leaderboard.callback(self.cog, self.ctx, all_time=True)

        text = self._sent_text()
        self.assertIn("All-Time", text)
        self.assertNotIn("Test Season", text)

    async def test_profile(self):
        self.stack.game.handle_guess(123, "Test", "wrong")
        self.stack.game.handle_guess(123, "Test", "4")

        await self.cog.profile.callback(self.cog, self.ctx)

        score = self.stack.player_manager.get_player("123").score
        text = self._sent_text()
        self.assertIn("-- Your stats, Test --", text)
        self.assertIn(f"Score:         {score}", text)
        self.assertIn("Correct:       1/2 (50.0%)", text)
        self.assertIs(self.bot.send_message.await_args.kwargs["ephemeral"], True)

    async def test_game_group(self):
        """Test the game group command sends help."""
        self.ctx.invoked_subcommand = None
        await self.cog.game.callback(self.cog, self.ctx)
        self.ctx.send_help.assert_awaited_once_with(self.ctx.command)

    async def test_setup(self):
        """Test the setup function."""
        from src.cogs.game import setup

        mock_bot = MagicMock()
        mock_bot.add_cog = AsyncMock()
        await setup(mock_bot)
        mock_bot.add_cog.assert_called_once()


if __name__ == "__main__":
    unittest.main()
