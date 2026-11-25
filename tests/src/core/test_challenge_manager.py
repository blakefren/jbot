"""
Tests for ChallengeManager backed by a real in-memory database.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from db.database import Database
from src.cfg.main import ConfigReader
from src.core.challenge_manager import ChallengeManager, CHALLENGE_POOL
from src.core.data_manager import DataManager
from src.core.season import SeasonChallenge


class _ChallengeTestCase(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.data_manager = DataManager(self.db)
        # ConfigReader is an external boundary (reads .env / sources.toml)
        self.config = MagicMock(spec=ConfigReader)
        self.manager = ChallengeManager(self.data_manager, self.config)
        self.season_id = self.data_manager.create_season(
            "January 2026", "2026-01-01", "2026-01-31"
        )
        self.data_manager.create_player("1", "Alice")

    def tearDown(self):
        self.db.close()

    def _set_progress(self, **fields):
        if "challenge_progress" in fields:
            fields["challenge_progress"] = json.dumps(fields["challenge_progress"])
        self.data_manager.update_season_score("1", self.season_id, **fields)


class TestChallengeManager(_ChallengeTestCase):
    """Test ChallengeManager functionality."""

    def test_create_season_challenge_no_previous(self):
        """Test creating challenge when no previous challenge exists."""
        # random.choice is patched to make the selection deterministic
        with patch("random.choice", side_effect=lambda pool: pool[0]):
            self.manager.create_season_challenge(self.season_id)

        stored = self.data_manager.get_season_challenge(self.season_id)
        self.assertEqual(stored.challenge_name, "Speed Demon")
        self.assertEqual(stored.completion_criteria, CHALLENGE_POOL[0]["criteria"])

    def test_create_season_challenge_avoid_previous(self):
        """Test that new challenge doesn't repeat previous month."""
        previous_id = self.data_manager.create_season(
            "December 2025", "2025-12-01", "2025-12-31"
        )
        self.data_manager.create_season_challenge(
            previous_id,
            "Speed Demon",
            "Answer 10 questions before hint",
            "⚡",
            {"before_hint_count": 10},
        )

        # Picking the first candidate would be Speed Demon if it weren't filtered out
        with patch("random.choice", side_effect=lambda pool: pool[0]):
            self.manager.create_season_challenge(self.season_id)

        stored = self.data_manager.get_season_challenge(self.season_id)
        self.assertNotEqual(stored.challenge_name, "Speed Demon")
        self.assertEqual(stored.challenge_name, CHALLENGE_POOL[1]["name"])

    def test_check_challenge_progress_before_hint_count(self):
        """Test checking progress for before_hint_count challenge."""
        challenge = SeasonChallenge(
            1,
            1,
            "Speed Demon",
            "Answer 10 questions before hint",
            "⚡",
            {"before_hint_count": 10},
        )
        self._set_progress(challenge_progress={"before_hint_answers": 7})

        is_complete, current, goal = self.manager.check_challenge_progress(
            "1", self.season_id, challenge
        )

        self.assertFalse(is_complete)
        self.assertEqual(current, 7)
        self.assertEqual(goal, 10)

        # Test completion
        self._set_progress(challenge_progress={"before_hint_answers": 10})
        is_complete, current, goal = self.manager.check_challenge_progress(
            "1", self.season_id, challenge
        )
        self.assertTrue(is_complete)

    def test_check_challenge_progress_streak_threshold(self):
        """Test checking progress for streak_threshold challenge."""
        challenge = SeasonChallenge(
            1,
            1,
            "Perfectionist",
            "Achieve a 7-day streak",
            "🔥",
            {"streak_threshold": 7},
        )
        self._set_progress(best_streak=5)

        is_complete, current, goal = self.manager.check_challenge_progress(
            "1", self.season_id, challenge
        )

        self.assertFalse(is_complete)
        self.assertEqual(current, 5)
        self.assertEqual(goal, 7)

    def test_check_challenge_progress_first_answer_count(self):
        """Test checking progress for first_answer_count challenge."""
        challenge = SeasonChallenge(
            1,
            1,
            "First Blood",
            "Be first to answer 5 questions",
            "🏆",
            {"first_answer_count": 5},
        )
        self._set_progress(first_answers=4)

        is_complete, current, goal = self.manager.check_challenge_progress(
            "1", self.season_id, challenge
        )

        self.assertFalse(is_complete)
        self.assertEqual(current, 4)
        self.assertEqual(goal, 5)

    def test_check_challenge_progress_questions_answered(self):
        """Test checking progress for questions_answered challenge."""
        challenge = SeasonChallenge(
            1,
            1,
            "Marathon Runner",
            "Answer all questions this month",
            "🏃",
            {"questions_answered": 30},
        )
        self._set_progress(questions_answered=28)

        is_complete, current, goal = self.manager.check_challenge_progress(
            "1", self.season_id, challenge
        )

        self.assertFalse(is_complete)
        self.assertEqual(current, 28)
        self.assertEqual(goal, 30)

    def test_check_challenge_progress_correct_answers(self):
        """Test checking progress for correct_answers challenge."""
        challenge = SeasonChallenge(
            1,
            1,
            "Ace",
            "Answer 25 questions correctly",
            "🎯",
            {"correct_answers": 25},
        )
        self._set_progress(correct_answers=20)

        is_complete, current, goal = self.manager.check_challenge_progress(
            "1", self.season_id, challenge
        )

        self.assertFalse(is_complete)
        self.assertEqual(current, 20)
        self.assertEqual(goal, 25)

    def test_check_challenge_progress_first_try_correct(self):
        """Test checking progress for first_try_correct challenge."""
        challenge = SeasonChallenge(
            1,
            1,
            "Sharpshooter",
            "Get 15 first-try correct answers",
            "🎪",
            {"first_try_correct": 15},
        )
        self._set_progress(challenge_progress={"first_try_correct": 12})

        is_complete, current, goal = self.manager.check_challenge_progress(
            "1", self.season_id, challenge
        )

        self.assertFalse(is_complete)
        self.assertEqual(current, 12)
        self.assertEqual(goal, 15)

    def test_update_challenge_progress(self):
        """Test updating challenge progress."""
        self.data_manager.initialize_player_season_score("1", self.season_id)

        self.manager.update_challenge_progress(
            "1", self.season_id, "before_hint_answer", 1
        )
        self.manager.update_challenge_progress(
            "1", self.season_id, "before_hint_answer", 2
        )
        self.manager.update_challenge_progress(
            "1", self.season_id, "first_try_correct", 1
        )

        stored = self.data_manager.get_player_season_score("1", self.season_id)
        self.assertEqual(
            stored.challenge_progress,
            {"before_hint_answers": 3, "first_try_correct": 1},
        )

    def test_update_challenge_progress_creates_missing_season_score(self):
        """A player without a season score row gets one on first progress update."""
        self.assertIsNone(
            self.data_manager.get_player_season_score("1", self.season_id)
        )

        self.manager.update_challenge_progress(
            "1", self.season_id, "before_hint_answer", 1
        )

        stored = self.data_manager.get_player_season_score("1", self.season_id)
        self.assertEqual(stored.challenge_progress, {"before_hint_answers": 1})

    def test_get_challenge_display_incomplete(self):
        """Test challenge display for incomplete challenge."""
        challenge = SeasonChallenge(
            1,
            1,
            "Speed Demon",
            "Answer 10 questions before hint",
            "⚡",
            {"before_hint_count": 10},
        )
        self._set_progress(challenge_progress={"before_hint_answers": 6})

        result = self.manager.get_challenge_display("1", self.season_id, challenge)

        self.assertIn("⚡", result)
        self.assertIn("Speed Demon", result)
        self.assertIn("6/10", result)

    def test_get_challenge_display_completed(self):
        """Test challenge display for completed challenge."""
        challenge = SeasonChallenge(
            1,
            1,
            "Speed Demon",
            "Answer 10 questions before hint",
            "⚡",
            {"before_hint_count": 10},
        )
        self._set_progress(challenge_progress={"before_hint_answers": 10})

        result = self.manager.get_challenge_display("1", self.season_id, challenge)

        self.assertIn("✅", result)


class TestChallengeManagerEdgeCases(_ChallengeTestCase):
    """Test edge cases and error conditions."""

    def test_check_challenge_progress_no_season_score(self):
        """Test checking progress with no season score."""
        challenge = SeasonChallenge(
            1,
            1,
            "Speed Demon",
            "Answer 10 questions before hint",
            "⚡",
            {"before_hint_count": 10},
        )

        is_complete, current, goal = self.manager.check_challenge_progress(
            "1", self.season_id, challenge
        )

        self.assertFalse(is_complete)
        self.assertEqual(current, 0)
        self.assertEqual(goal, 10)

    def test_challenge_pool_structure(self):
        """Test that challenge pool has correct structure."""
        self.assertEqual(len(CHALLENGE_POOL), 6)

        required_keys = ["name", "description", "emoji", "criteria"]
        for challenge in CHALLENGE_POOL:
            for key in required_keys:
                self.assertIn(key, challenge)

            # Each challenge should have exactly one criterion
            self.assertEqual(len(challenge["criteria"]), 1)


if __name__ == "__main__":
    unittest.main()
