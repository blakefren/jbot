"""
Integration tests for DataManager season-related methods.

All tests use a real in-memory SQLite database with the actual schema, so column
name errors, schema mismatches and broken SQL are caught automatically.
"""

import unittest
from datetime import date

from db.database import Database
from src.core.data_manager import DataManager
from src.core.season import Season, SeasonScore, SeasonChallenge


def _setup_db() -> tuple[Database, DataManager]:
    db = Database(":memory:")
    dm = DataManager(db)
    dm.initialize_database()
    return db, dm


def _create_player(dm: DataManager, player_id: str, name: str = "Player") -> None:
    dm.create_player(player_id, name)


def _create_season(
    dm: DataManager,
    name: str = "January 2026",
    start: str = "2026-01-01",
    end: str = "2026-01-31",
) -> int:
    return dm.create_season(name, start, end)


class TestDataManagerSeasonCRUD(unittest.TestCase):
    """Tests for basic season create/read/update/end operations."""

    def setUp(self):
        self.db, self.dm = _setup_db()

    def tearDown(self):
        self.db.close()

    # --- create_season / get_current_season ---

    def test_create_season_returns_id(self):
        season_id = _create_season(self.dm)
        self.assertIsInstance(season_id, int)
        self.assertGreater(season_id, 0)

    def test_create_season_deactivates_previous(self):
        id1 = _create_season(self.dm, "Jan 2026", "2026-01-01", "2026-01-31")
        id2 = _create_season(self.dm, "Feb 2026", "2026-02-01", "2026-02-28")

        season1 = self.dm.get_season_by_id(id1)
        season2 = self.dm.get_season_by_id(id2)

        self.assertFalse(season1.is_active)
        self.assertTrue(season2.is_active)

    def test_get_current_season_returns_active(self):
        _create_season(self.dm)
        season = self.dm.get_current_season()
        self.assertIsNotNone(season)
        self.assertIsInstance(season, Season)
        self.assertTrue(season.is_active)
        self.assertEqual(season.season_name, "January 2026")

    def test_get_current_season_returns_none_when_empty(self):
        result = self.dm.get_current_season()
        self.assertIsNone(result)

    def test_get_season_by_id(self):
        season_id = _create_season(self.dm, "March 2026", "2026-03-01", "2026-03-31")
        season = self.dm.get_season_by_id(season_id)
        self.assertIsNotNone(season)
        self.assertEqual(season.season_id, season_id)
        self.assertEqual(season.season_name, "March 2026")
        self.assertEqual(season.start_date, date(2026, 3, 1))
        self.assertEqual(season.end_date, date(2026, 3, 31))

    def test_get_season_by_id_missing_returns_none(self):
        result = self.dm.get_season_by_id(9999)
        self.assertIsNone(result)

    def test_get_all_seasons_returns_all(self):
        _create_season(self.dm, "Jan 2026", "2026-01-01", "2026-01-31")
        _create_season(self.dm, "Feb 2026", "2026-02-01", "2026-02-28")
        seasons = self.dm.get_all_seasons()
        self.assertEqual(len(seasons), 2)
        self.assertIsInstance(seasons[0], Season)

    def test_get_all_seasons_empty(self):
        self.assertEqual(self.dm.get_all_seasons(), [])

    def test_end_season_marks_inactive(self):
        season_id = _create_season(self.dm)
        self.dm.end_season(season_id)
        season = self.dm.get_season_by_id(season_id)
        self.assertFalse(season.is_active)

    def test_get_current_season_none_after_end(self):
        season_id = _create_season(self.dm)
        self.dm.end_season(season_id)
        self.assertIsNone(self.dm.get_current_season())


class TestDataManagerSeasonScores(unittest.TestCase):
    """Tests for player season score operations."""

    def setUp(self):
        self.db, self.dm = _setup_db()
        _create_player(self.dm, "p1", "Alice")
        _create_player(self.dm, "p2", "Bob")
        self.season_id = _create_season(self.dm)

    def tearDown(self):
        self.db.close()

    # --- initialize_player_season_score / get_player_season_score ---

    def test_initialize_player_season_score_creates_row(self):
        self.dm.initialize_player_season_score("p1", self.season_id)
        score = self.dm.get_player_season_score("p1", self.season_id)
        self.assertIsNotNone(score)
        self.assertIsInstance(score, SeasonScore)
        self.assertEqual(score.player_id, "p1")
        self.assertEqual(score.points, 0)

    def test_initialize_player_season_score_idempotent(self):
        """Calling twice should not raise or create duplicates."""
        self.dm.initialize_player_season_score("p1", self.season_id)
        self.dm.initialize_player_season_score("p1", self.season_id)
        score = self.dm.get_player_season_score("p1", self.season_id)
        self.assertIsNotNone(score)
        self.assertEqual(score.points, 0)

    def test_get_player_season_score_missing_returns_none(self):
        result = self.dm.get_player_season_score("p1", self.season_id)
        self.assertIsNone(result)

    # --- update_season_score ---

    def test_update_season_score_sets_fields(self):
        self.dm.initialize_player_season_score("p1", self.season_id)
        self.dm.update_season_score("p1", self.season_id, points=500, correct_answers=5)
        score = self.dm.get_player_season_score("p1", self.season_id)
        self.assertEqual(score.points, 500)
        self.assertEqual(score.correct_answers, 5)

    def test_update_season_score_auto_initializes(self):
        """update_season_score should create the row if it doesn't exist."""
        self.dm.update_season_score("p1", self.season_id, points=100)
        score = self.dm.get_player_season_score("p1", self.season_id)
        self.assertIsNotNone(score)
        self.assertEqual(score.points, 100)

    def test_update_season_score_no_kwargs_is_noop(self):
        self.dm.initialize_player_season_score("p1", self.season_id)
        # Should not raise
        self.dm.update_season_score("p1", self.season_id)
        score = self.dm.get_player_season_score("p1", self.season_id)
        self.assertEqual(score.points, 0)

    # --- increment_season_stat ---

    def test_increment_season_stat(self):
        self.dm.initialize_player_season_score("p1", self.season_id)
        self.dm.increment_season_stat("p1", self.season_id, "points", 50)
        self.dm.increment_season_stat("p1", self.season_id, "points", 30)
        score = self.dm.get_player_season_score("p1", self.season_id)
        self.assertEqual(score.points, 80)

    def test_increment_season_stat_default_amount(self):
        self.dm.initialize_player_season_score("p1", self.season_id)
        self.dm.increment_season_stat("p1", self.season_id, "correct_answers")
        score = self.dm.get_player_season_score("p1", self.season_id)
        self.assertEqual(score.correct_answers, 1)

    def test_increment_season_stat_auto_initializes(self):
        self.dm.increment_season_stat("p1", self.season_id, "questions_answered", 1)
        score = self.dm.get_player_season_score("p1", self.season_id)
        self.assertIsNotNone(score)
        self.assertEqual(score.questions_answered, 1)

    # --- get_season_scores ---

    def test_get_season_scores_ordered_by_points(self):
        self.dm.update_season_score("p2", self.season_id, points=300)
        self.dm.update_season_score("p1", self.season_id, points=500)
        scores = self.dm.get_season_scores(self.season_id)
        self.assertEqual(len(scores), 2)
        self.assertEqual(scores[0].points, 500)
        self.assertEqual(scores[1].points, 300)

    def test_get_season_scores_respects_limit(self):
        for i in range(1, 6):
            _create_player(self.dm, f"extra{i}", f"Extra{i}")
            self.dm.update_season_score(f"extra{i}", self.season_id, points=i * 10)
        scores = self.dm.get_season_scores(self.season_id, limit=3)
        self.assertEqual(len(scores), 3)

    def test_get_season_scores_empty(self):
        scores = self.dm.get_season_scores(self.season_id)
        self.assertEqual(scores, [])

    # --- reset_all_player_season_scores ---

    def test_reset_all_player_season_scores(self):
        self.dm.update_season_score("p1", self.season_id, points=200)
        self.dm.reset_all_player_season_scores()
        # reset_all_player_season_scores updates the players table season_score column
        rows = self.db.execute_query(
            "SELECT season_score, answer_streak FROM players WHERE id = 'p1'"
        )
        self.assertEqual(rows[0]["season_score"], 0)
        self.assertEqual(rows[0]["answer_streak"], 0)


class TestDataManagerTrophies(unittest.TestCase):
    """Tests for trophy awarding and retrieval."""

    def setUp(self):
        self.db, self.dm = _setup_db()
        _create_player(self.dm, "p1", "Alice")
        _create_player(self.dm, "p2", "Bob")
        _create_player(self.dm, "p3", "Carol")
        self.season_id = _create_season(self.dm)

    def tearDown(self):
        self.db.close()

    def test_finalize_season_rankings_awards_trophies(self):
        self.dm.update_season_score("p1", self.season_id, points=500)
        self.dm.update_season_score("p2", self.season_id, points=300)
        self.dm.update_season_score("p3", self.season_id, points=100)

        self.dm.finalize_season_rankings(self.season_id)

        s1 = self.dm.get_player_season_score("p1", self.season_id)
        s2 = self.dm.get_player_season_score("p2", self.season_id)
        s3 = self.dm.get_player_season_score("p3", self.season_id)

        self.assertEqual(s1.trophy, "gold")
        self.assertEqual(s2.trophy, "silver")
        self.assertEqual(s3.trophy, "bronze")

    def test_finalize_season_rankings_assigns_ranks(self):
        self.dm.update_season_score("p1", self.season_id, points=500)
        self.dm.update_season_score("p2", self.season_id, points=300)

        self.dm.finalize_season_rankings(self.season_id)

        s1 = self.dm.get_player_season_score("p1", self.season_id)
        s2 = self.dm.get_player_season_score("p2", self.season_id)

        self.assertEqual(s1.final_rank, 1)
        self.assertEqual(s2.final_rank, 2)

    def test_finalize_season_rankings_tie_handling(self):
        """Tied players should share the same rank and trophy."""
        self.dm.update_season_score("p1", self.season_id, points=500)
        self.dm.update_season_score("p2", self.season_id, points=500)
        self.dm.update_season_score("p3", self.season_id, points=100)

        self.dm.finalize_season_rankings(self.season_id)

        s1 = self.dm.get_player_season_score("p1", self.season_id)
        s2 = self.dm.get_player_season_score("p2", self.season_id)
        s3 = self.dm.get_player_season_score("p3", self.season_id)

        self.assertEqual(s1.final_rank, 1)
        self.assertEqual(s2.final_rank, 1)
        self.assertEqual(s3.final_rank, 3)
        # Both tied players at rank 1 get gold
        self.assertEqual(s1.trophy, "gold")
        self.assertEqual(s2.trophy, "gold")
        # Rank 3 still receives bronze (within trophy_positions=3)
        self.assertEqual(s3.trophy, "bronze")

    def test_finalize_season_rankings_custom_positions(self):
        """Only top 1 should receive a trophy when trophy_positions=1."""
        self.dm.update_season_score("p1", self.season_id, points=500)
        self.dm.update_season_score("p2", self.season_id, points=300)

        self.dm.finalize_season_rankings(self.season_id, trophy_positions=1)

        s1 = self.dm.get_player_season_score("p1", self.season_id)
        s2 = self.dm.get_player_season_score("p2", self.season_id)

        self.assertEqual(s1.trophy, "gold")
        self.assertIsNone(s2.trophy)

    def test_finalize_season_rankings_empty(self):
        """Finalizing with no participants should not raise."""
        self.dm.finalize_season_rankings(self.season_id)

    def test_get_player_trophies_multiple_seasons(self):
        id2 = _create_season(self.dm, "Feb 2026", "2026-02-01", "2026-02-28")

        self.dm.update_season_score("p1", self.season_id, points=1000)
        self.dm.finalize_season_rankings(self.season_id)

        self.dm.update_season_score("p1", id2, points=900)
        self.dm.finalize_season_rankings(id2)

        trophies = self.dm.get_player_trophies("p1")
        self.assertEqual(len(trophies), 2)
        for t in trophies:
            self.assertEqual(t["trophy"], "gold")

    def test_get_player_trophies_none_won(self):
        self.dm.update_season_score("p2", self.season_id, points=500)
        self.dm.finalize_season_rankings(self.season_id)

        trophies = self.dm.get_player_trophies("p1")
        self.assertEqual(trophies, [])

    def test_get_trophy_counts(self):
        id2 = _create_season(self.dm, "Feb 2026", "2026-02-01", "2026-02-28")

        self.dm.update_season_score("p1", self.season_id, points=1000)
        self.dm.update_season_score("p2", self.season_id, points=500)
        self.dm.finalize_season_rankings(self.season_id)

        self.dm.update_season_score("p1", id2, points=200)
        self.dm.update_season_score("p2", id2, points=900)
        self.dm.finalize_season_rankings(id2)

        p1_counts = self.dm.get_trophy_counts("p1")
        self.assertEqual(p1_counts["gold"], 1)
        self.assertEqual(p1_counts["silver"], 1)
        self.assertEqual(p1_counts["bronze"], 0)

    def test_get_trophy_counts_empty(self):
        counts = self.dm.get_trophy_counts("p1")
        self.assertEqual(counts, {"gold": 0, "silver": 0, "bronze": 0})


class TestDataManagerSeasonChallenges(unittest.TestCase):
    """Tests for season challenge CRUD."""

    def setUp(self):
        self.db, self.dm = _setup_db()
        self.season_id = _create_season(self.dm)

    def tearDown(self):
        self.db.close()

    def test_create_and_get_season_challenge(self):
        challenge_id = self.dm.create_season_challenge(
            self.season_id,
            "Speed Demon",
            "Answer 10 questions before hint",
            "⚡",
            {"type": "before_hint", "target": 10},
        )
        self.assertIsInstance(challenge_id, int)
        self.assertGreater(challenge_id, 0)

        challenge = self.dm.get_season_challenge(self.season_id)
        self.assertIsNotNone(challenge)
        self.assertIsInstance(challenge, SeasonChallenge)
        self.assertEqual(challenge.challenge_name, "Speed Demon")
        self.assertEqual(challenge.badge_emoji, "⚡")
        self.assertEqual(challenge.completion_criteria["target"], 10)

    def test_get_season_challenge_missing_returns_none(self):
        result = self.dm.get_season_challenge(self.season_id)
        self.assertIsNone(result)

    def test_get_season_challenge_wrong_season_returns_none(self):
        self.dm.create_season_challenge(
            self.season_id, "Hard Worker", "Win 5 days", "💪", {"days": 5}
        )
        result = self.dm.get_season_challenge(9999)
        self.assertIsNone(result)


class TestDataManagerLifetimeStats(unittest.TestCase):
    """Tests for lifetime stat updates."""

    def setUp(self):
        self.db, self.dm = _setup_db()
        _create_player(self.dm, "p1", "Alice")

    def tearDown(self):
        self.db.close()

    def test_update_lifetime_stats_single_field(self):
        self.dm.update_lifetime_stats("p1", score=999)
        player = self.dm.get_player("p1")
        self.assertEqual(player.score, 999)

    def test_update_lifetime_stats_multiple_fields(self):
        self.dm.update_lifetime_stats("p1", lifetime_questions=50, lifetime_correct=40)
        player = self.dm.get_player("p1")
        self.assertEqual(player.lifetime_questions, 50)
        self.assertEqual(player.lifetime_correct, 40)

    def test_update_lifetime_stats_no_kwargs_noop(self):
        self.dm.update_lifetime_stats("p1")
        player = self.dm.get_player("p1")
        self.assertEqual(player.score, 0)

    def test_increment_lifetime_stat_default(self):
        self.dm.increment_lifetime_stat("p1", "lifetime_questions")
        self.dm.increment_lifetime_stat("p1", "lifetime_questions")
        player = self.dm.get_player("p1")
        self.assertEqual(player.lifetime_questions, 2)

    def test_increment_lifetime_stat_custom_amount(self):
        self.dm.increment_lifetime_stat("p1", "lifetime_correct", 5)
        player = self.dm.get_player("p1")
        self.assertEqual(player.lifetime_correct, 5)


class TestDataManagerGetStreakKeepers(unittest.TestCase):
    """Tests for get_streak_keepers — drives end-of-day streak reset logic."""

    def setUp(self):
        self.db, self.dm = _setup_db()
        _create_player(self.dm, "p1", "Alice")
        _create_player(self.dm, "p2", "Bob")
        _create_player(self.dm, "p3", "Carol")

        # Insert a question and daily_question
        self.db.execute_update(
            """INSERT INTO questions (question_text, answer_text, category, value, source, question_hash)
               VALUES ('Q?', 'A', 'Cat', 100, 'test', 'hash1')"""
        )
        self.db.execute_update(
            "INSERT INTO daily_questions (question_id, sent_at) VALUES (1, '2026-01-01')"
        )
        self.dq_id = self.db.execute_query("SELECT id FROM daily_questions LIMIT 1")[0][
            "id"
        ]

    def tearDown(self):
        self.db.close()

    def test_correct_guesser_is_keeper(self):
        self.db.execute_update(
            "INSERT INTO guesses (daily_question_id, player_id, guess_text, is_correct) VALUES (?, 'p1', 'A', 1)",
            (self.dq_id,),
        )
        keepers = self.dm.get_streak_keepers(self.dq_id)
        self.assertIn("p1", keepers)

    def test_incorrect_guesser_is_not_keeper(self):
        self.db.execute_update(
            "INSERT INTO guesses (daily_question_id, player_id, guess_text, is_correct) VALUES (?, 'p2', 'wrong', 0)",
            (self.dq_id,),
        )
        keepers = self.dm.get_streak_keepers(self.dq_id)
        self.assertNotIn("p2", keepers)

    def test_rest_user_is_keeper(self):
        self.db.execute_update(
            "INSERT INTO powerup_usage (user_id, powerup_type, question_id) VALUES ('p3', 'rest', ?)",
            (self.dq_id,),
        )
        keepers = self.dm.get_streak_keepers(self.dq_id)
        self.assertIn("p3", keepers)

    def test_empty_returns_empty_set(self):
        keepers = self.dm.get_streak_keepers(self.dq_id)
        self.assertEqual(keepers, set())

    def test_both_correct_and_rest_included(self):
        self.db.execute_update(
            "INSERT INTO guesses (daily_question_id, player_id, guess_text, is_correct) VALUES (?, 'p1', 'A', 1)",
            (self.dq_id,),
        )
        self.db.execute_update(
            "INSERT INTO powerup_usage (user_id, powerup_type, question_id) VALUES ('p3', 'rest', ?)",
            (self.dq_id,),
        )
        keepers = self.dm.get_streak_keepers(self.dq_id)
        self.assertEqual(keepers, {"p1", "p3"})


if __name__ == "__main__":
    unittest.main()
