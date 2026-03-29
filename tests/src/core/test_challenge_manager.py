"""
Unit tests for ChallengeManager.
"""

import unittest
from unittest.mock import MagicMock, patch
from src.core.challenge_manager import ChallengeManager, CHALLENGE_POOL
from src.core.data_manager import DataManager
from src.cfg.main import ConfigReader
from src.core.season import SeasonChallenge, SeasonScore


class TestChallengeManager(unittest.TestCase):
    """Test ChallengeManager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_data_manager = MagicMock(spec=DataManager)
        self.mock_config = MagicMock(spec=ConfigReader)
        self.manager = ChallengeManager(self.mock_data_manager, self.mock_config)

    def test_create_season_challenge_no_previous(self):
        """Test creating challenge when no previous challenge exists."""
        self.mock_data_manager.get_all_seasons.return_value = [
            MagicMock(season_id=1)
        ]  # Only one season
        self.mock_data_manager.get_season_challenge.return_value = None

        with patch("random.choice") as mock_choice:
            mock_choice.return_value = CHALLENGE_POOL[0]
            result = self.manager.create_season_challenge(1)

        self.mock_data_manager.create_season_challenge.assert_called_once()
        call_kwargs = self.mock_data_manager.create_season_challenge.call_args[1]
        self.assertEqual(call_kwargs["season_id"], 1)
        self.assertEqual(call_kwargs["challenge_name"], "Speed Demon")

    def test_create_season_challenge_avoid_previous(self):
        """Test that new challenge doesn't repeat previous month."""
        previous_challenge = SeasonChallenge(
            1,
            0,  # Previous season
            "Speed Demon",
            "Answer 10 questions before hint",
            "⚡",
            {"before_hint_count": 10},
        )
        self.mock_data_manager.get_all_seasons.return_value = [
            MagicMock(season_id=1),
            MagicMock(season_id=0),
        ]
        self.mock_data_manager.get_season_challenge.return_value = previous_challenge

        with patch("random.choice") as mock_choice:
            # Should only be called with challenges excluding Speed Demon
            available_challenges = [
                c for c in CHALLENGE_POOL if c["name"] != "Speed Demon"
            ]
            mock_choice.return_value = available_challenges[0]

            result = self.manager.create_season_challenge(1)

        # Verify the choice was made from filtered list
        call_args = mock_choice.call_args[0][0]
        challenge_names = [c["name"] for c in call_args]
        self.assertNotIn("Speed Demon", challenge_names)

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
        season_score = SeasonScore(
            player_id="1",
            season_id=1,
            challenge_progress={"before_hint_answers": 7},
        )
        self.mock_data_manager.get_player_season_score.return_value = season_score

        is_complete, current, goal = self.manager.check_challenge_progress(
            "1", 1, challenge
        )

        self.assertFalse(is_complete)
        self.assertEqual(current, 7)
        self.assertEqual(goal, 10)

        # Test completion
        season_score.challenge_progress["before_hint_answers"] = 10
        is_complete, current, goal = self.manager.check_challenge_progress(
            "1", 1, challenge
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
        season_score = SeasonScore(player_id="1", season_id=1, best_streak=5)
        self.mock_data_manager.get_player_season_score.return_value = season_score

        is_complete, current, goal = self.manager.check_challenge_progress(
            "1", 1, challenge
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
        season_score = SeasonScore(player_id="1", season_id=1, first_answers=4)
        self.mock_data_manager.get_player_season_score.return_value = season_score

        is_complete, current, goal = self.manager.check_challenge_progress(
            "1", 1, challenge
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
        season_score = SeasonScore(player_id="1", season_id=1, questions_answered=28)
        self.mock_data_manager.get_player_season_score.return_value = season_score

        is_complete, current, goal = self.manager.check_challenge_progress(
            "1", 1, challenge
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
        season_score = SeasonScore(player_id="1", season_id=1, correct_answers=20)
        self.mock_data_manager.get_player_season_score.return_value = season_score

        is_complete, current, goal = self.manager.check_challenge_progress(
            "1", 1, challenge
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
        season_score = SeasonScore(
            player_id="1",
            season_id=1,
            challenge_progress={"first_try_correct": 12},
        )
        self.mock_data_manager.get_player_season_score.return_value = season_score

        is_complete, current, goal = self.manager.check_challenge_progress(
            "1", 1, challenge
        )

        self.assertFalse(is_complete)
        self.assertEqual(current, 12)
        self.assertEqual(goal, 15)

    def test_update_challenge_progress(self):
        """Test updating challenge progress."""
        season_score = SeasonScore(player_id="1", season_id=1)
        self.mock_data_manager.get_player_season_score.return_value = season_score

        self.manager.update_challenge_progress("1", 1, "before_hint_answer", 1)

        self.mock_data_manager.update_season_score.assert_called_once()

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
        season_score = SeasonScore(
            player_id="1",
            season_id=1,
            challenge_progress={"before_hint_answers": 6},
        )
        self.mock_data_manager.get_player_season_score.return_value = season_score

        result = self.manager.get_challenge_display("1", 1, challenge)

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
        season_score = SeasonScore(
            player_id="1",
            season_id=1,
            challenge_progress={"before_hint_answers": 10},
        )
        self.mock_data_manager.get_player_season_score.return_value = season_score

        result = self.manager.get_challenge_display("1", 1, challenge)

        self.assertIn("✅", result)


class TestChallengeManagerEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_data_manager = MagicMock(spec=DataManager)
        self.mock_config = MagicMock(spec=ConfigReader)
        self.manager = ChallengeManager(self.mock_data_manager, self.mock_config)

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
        self.mock_data_manager.get_player_season_score.return_value = None

        is_complete, current, goal = self.manager.check_challenge_progress(
            "1", 1, challenge
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
