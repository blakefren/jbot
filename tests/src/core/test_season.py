"""
Unit tests for Season data models.
"""

import unittest
from datetime import date
from src.core.season import Season, SeasonScore


class TestSeason(unittest.TestCase):
    """Test Season dataclass."""

    def test_season_creation(self):
        """Test creating a Season object."""
        season = Season(
            season_id=1,
            season_name="January 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            is_active=True,
        )

        self.assertEqual(season.season_id, 1)
        self.assertEqual(season.season_name, "January 2026")
        self.assertEqual(season.start_date, date(2026, 1, 1))
        self.assertEqual(season.end_date, date(2026, 1, 31))
        self.assertTrue(season.is_active)

    def test_season_from_db_row(self):
        """Test creating Season from database row."""
        row = {
            "season_id": 2,
            "season_name": "February 2026",
            "start_date": "2026-02-01",
            "end_date": "2026-02-28",
            "is_active": 0,
        }

        season = Season.from_db_row(row)

        self.assertEqual(season.season_id, 2)
        self.assertEqual(season.season_name, "February 2026")
        self.assertEqual(season.start_date, date(2026, 2, 1))
        self.assertEqual(season.end_date, date(2026, 2, 28))
        self.assertFalse(season.is_active)

    def test_season_str(self):
        """Test string representation."""
        season = Season(1, "January 2026", date(2026, 1, 1), date(2026, 1, 31), True)
        expected = "January 2026 (2026-01-01 to 2026-01-31)"
        self.assertEqual(str(season), expected)


class TestSeasonScore(unittest.TestCase):
    """Test SeasonScore dataclass."""

    def test_season_score_creation(self):
        """Test creating a SeasonScore object."""
        score = SeasonScore(
            player_id="123",
            season_id=1,
            points=500,
            questions_answered=10,
            correct_answers=8,
            first_answers=2,
        )

        self.assertEqual(score.player_id, "123")
        self.assertEqual(score.season_id, 1)
        self.assertEqual(score.points, 500)
        self.assertEqual(score.questions_answered, 10)
        self.assertEqual(score.correct_answers, 8)
        self.assertEqual(score.first_answers, 2)

    def test_season_score_defaults(self):
        """Test default values."""
        score = SeasonScore(player_id="123", season_id=1)

        self.assertEqual(score.points, 0)
        self.assertEqual(score.questions_answered, 0)
        self.assertEqual(score.current_streak, 0)
        self.assertIsNone(score.final_rank)
        self.assertIsNone(score.trophy)

    def test_season_score_from_db_row(self):
        """Test creating SeasonScore from database row."""
        row = {
            "player_id": "456",
            "season_id": 2,
            "points": 1000,
            "questions_answered": 20,
            "correct_answers": 15,
            "first_answers": 5,
            "current_streak": 3,
            "best_streak": 7,
            "final_rank": 1,
            "trophy": "gold",
        }

        score = SeasonScore.from_db_row(row)

        self.assertEqual(score.player_id, "456")
        self.assertEqual(score.points, 1000)
        self.assertEqual(score.trophy, "gold")

    def test_trophy_emoji_property(self):
        """Test trophy_emoji property."""
        gold = SeasonScore("1", 1, trophy="gold")
        silver = SeasonScore("2", 1, trophy="silver")
        bronze = SeasonScore("3", 1, trophy="bronze")
        none_trophy = SeasonScore("4", 1, trophy=None)

        self.assertEqual(gold.trophy_emoji, "🥇")
        self.assertEqual(silver.trophy_emoji, "🥈")
        self.assertEqual(bronze.trophy_emoji, "🥉")
        self.assertEqual(none_trophy.trophy_emoji, "")


if __name__ == "__main__":
    unittest.main()
