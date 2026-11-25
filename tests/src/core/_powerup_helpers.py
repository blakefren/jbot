"""
Shared test helpers for PowerUpManager and GuessHandler test modules.

Centralises the config factory so that adding a new config key only requires
a single edit here rather than updating every test file individually, and
builds the real in-memory SQLite stack (Database, DataManager, PlayerManager)
the tests run against.
"""

from datetime import timedelta
from unittest.mock import MagicMock

from data.readers.question import Question
from db.database import Database
from src.core.data_manager import DataManager
from src.core.player_manager import PlayerManager


def make_config(
    steal_cost=3,
    retro_steal_cost=5,
    jinx_share_ratio=0.25,
    jinx_wrong_guess_penalty=5,
    rest_multiplier=0.2,
):
    """Return a MagicMock ConfigReader pre-loaded with standard test values."""
    cfg = MagicMock()

    values = {
        "JBOT_STEAL_STREAK_COST": str(steal_cost),
        "JBOT_RETRO_STEAL_STREAK_COST": str(retro_steal_cost),
        "JBOT_JINX_SHARE_RATIO": str(jinx_share_ratio),
        "JBOT_JINX_WRONG_GUESS_PENALTY": str(jinx_wrong_guess_penalty),
        "JBOT_BONUS_STREAK_PER_DAY": "5",
        "JBOT_BONUS_STREAK_CAP": "25",
        "JBOT_BONUS_BEFORE_HINT": "10",
        "JBOT_BONUS_FASTEST_CSV": "10,5,1",
        "JBOT_BONUS_TRY_CSV": "20,10,5",
        "JBOT_REST_MULTIPLIER": str(rest_multiplier),
        "JBOT_EMOJI_FASTEST": "🥇",
        "JBOT_EMOJI_FASTEST_CSV": "🥇,🥈,🥉",
        "JBOT_EMOJI_FIRST_TRY": "🎯",
        "JBOT_EMOJI_STREAK": "🔥",
        "JBOT_EMOJI_BEFORE_HINT": "🧠",
        "JBOT_EMOJI_JINXED": "🥶",
        "JBOT_EMOJI_SILENCED": "🤐",
        "JBOT_EMOJI_STOLEN_FROM": "💸",
        "JBOT_EMOJI_STEALING": "💰",
        "JBOT_EMOJI_REST": "😴",
        "JBOT_EMOJI_REST_WAKEUP": "⏰",
    }

    cfg.get.side_effect = lambda key, default=None: values.get(key, default)
    return cfg


class PersistedPlayers:
    """Read-only mapping view that loads each player fresh from the database."""

    def __init__(self, player_manager):
        self._player_manager = player_manager

    def __getitem__(self, player_id):
        player = self._player_manager.get_player(player_id)
        if player is None:
            raise KeyError(player_id)
        return player


class RealStack:
    """Real in-memory SQLite stack with seeded players and today's daily question.

    `players` is an iterable of (id, name, score, answer_streak) tuples.
    """

    def __init__(self, players, question=None):
        self.db = Database(":memory:")
        self.data_manager = DataManager(self.db)
        self.player_manager = PlayerManager(self.data_manager)
        self.players = PersistedPlayers(self.player_manager)
        for player_id, name, score, streak in players:
            self.data_manager.create_player(player_id, name)
            self.data_manager.update_lifetime_stats(
                player_id, score=score, answer_streak=streak
            )
        self.new_question_day(question)

    def new_question_day(self, question=None) -> int:
        """Log a fresh daily question (replacing today's) and return its id."""
        self.question = question or Question("What is 2 + 2?", "4", "Math", 100)
        self.question_id = self.data_manager.log_daily_question(
            self.question, force_new=True
        )
        _, _, self.question_db_id = self.data_manager.get_todays_daily_question()
        return self.question_id

    def set_streak(self, player_id, streak):
        self.data_manager.set_streak(player_id, streak)

    def mark_answered_today(self, player_id, question_id=None):
        """Persist a correct guess so the player counts as having answered today."""
        player = self.player_manager.get_player(player_id)
        self.data_manager.log_player_guess(
            player_id, player.name, question_id or self.question_id, "answer", True
        )

    def answer_on_earlier_day(self, player_id, days_ago=1):
        """Persist a correct guess on a daily question sent `days_ago` days back.

        days_ago=0 models an earlier question that was already answered today.
        """
        player = self.player_manager.get_player(player_id)
        sent_at = self.data_manager.get_today() - timedelta(days=days_ago)
        _, daily_question_id = self.db.execute_update(
            "INSERT INTO daily_questions (question_id, sent_at) VALUES (?, ?)",
            (self.question_db_id, sent_at),
        )
        self.data_manager.log_player_guess(
            player_id, player.name, daily_question_id, "answer", True
        )

    def send_hint(self):
        """Record the morning and reminder messages so today's hint counts as sent."""
        for status, offset in (
            ("morning_message", "-1 minute"),
            ("reminder_message", "+1 minute"),
        ):
            self.db.execute_update(
                "INSERT INTO messages (direction, method, recipient_sender, content, status, timestamp) "
                "VALUES ('outgoing', 'discord', 'channel', 'msg', ?, datetime('now', ?))",
                (status, offset),
            )

    def usages(self):
        """Every powerup_usage row as (user_id, powerup_type, target, question_id)."""
        rows = self.db.execute_query("SELECT * FROM powerup_usage ORDER BY id")
        return [
            (
                row["user_id"],
                row["powerup_type"],
                row["target_user_id"],
                row["question_id"],
            )
            for row in rows
        ]

    def close(self):
        self.db.close()


def make_stack(test_case, players, question=None) -> RealStack:
    """Build a RealStack that is closed automatically when the test finishes."""
    stack = RealStack(players, question)
    test_case.addCleanup(stack.close)
    return stack
