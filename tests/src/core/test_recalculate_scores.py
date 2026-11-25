import unittest
from unittest.mock import MagicMock, patch
from datetime import timedelta
from src.core.data_manager import DataManager
from src.core.game_runner import GameRunner
from src.core.player_manager import PlayerManager
from db.database import Database
from data.readers.question import Question
from tests.src.core._powerup_helpers import make_config


class TestRecalculateScores(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.addCleanup(self.db.close)
        self.data_manager = DataManager(self.db)
        self.player_manager = PlayerManager(self.data_manager)

        # ConfigReader reads .env, so a config double stands in for it.
        self.config = make_config()
        self.config.is_seasons_enabled.return_value = False
        # The question selector wraps datasets/Gemini and is unused by recalculation.
        with patch("src.core.game_runner.ConfigReader", return_value=self.config):
            self.game_runner = GameRunner(
                MagicMock(), self.data_manager, player_manager=self.player_manager
            )

    def _start_day(self, players=(), answer="800-899"):
        """
        Seed players, then log and activate today's question.  Logging the question
        snapshots the players seeded here.  Each player is (id[, name, score, streak, rest]).
        """
        for player in players:
            if isinstance(player, str):
                player = (player,)
            player_id, name, score, streak, rest = (
                *player,
                *(None, 0, 0, 0.0)[len(player) - 1 :],
            )
            self.data_manager.create_player(player_id, name or player_id)
            self.data_manager.update_lifetime_stats(
                player_id,
                score=score,
                answer_streak=streak,
                pending_rest_multiplier=rest,
            )
        question = Question(question="Q", answer=answer, category="C", clue_value=100)
        # A used-only question first so questions.id differs from daily_questions.id.
        self.data_manager.log_daily_question(
            Question(question="Used", answer="Used", category="C"),
            mark_as_used_only=True,
        )
        self.daily_question_id = self.data_manager.log_daily_question(question)
        _, _, self.question_db_id = self.data_manager.get_todays_daily_question()
        self.game_runner.daily_q = question
        self.game_runner.daily_question_id = self.daily_question_id
        self.game_runner.question_db_id = self.question_db_id

    def _deactivate_question(self):
        """Simulates the period after the evening message when no question is active."""
        self.game_runner.daily_q = None
        self.game_runner.daily_question_id = None
        self.game_runner.question_db_id = None

    def _guess(
        self, player_id, text, guessed_at="2023-01-01 10:00:00", is_correct=False
    ):
        self.data_manager.log_player_guess(
            player_id, player_id, self.daily_question_id, text, is_correct
        )
        self.db.execute_update(
            "UPDATE guesses SET guessed_at = ? WHERE id = (SELECT MAX(id) FROM guesses)",
            (guessed_at,),
        )

    def _rest(self, player_id, used_at="2023-01-01 09:00:00"):
        """Log a rest and apply its multiplier the way the live power-up does."""
        self.data_manager.log_powerup_usage(
            player_id, "rest", None, self.daily_question_id
        )
        self.db.execute_update(
            "UPDATE powerup_usage SET used_at = ? WHERE id = (SELECT MAX(id) FROM powerup_usage)",
            (used_at,),
        )
        self.data_manager.increment_pending_multiplier(player_id, 0.2)

    def _player(self, player_id):
        return self.data_manager.get_player(player_id)

    def _guess_is_correct(self, player_id):
        rows = self.db.execute_query(
            "SELECT is_correct FROM guesses WHERE player_id = ?", (player_id,)
        )
        return [bool(row["is_correct"]) for row in rows]

    def _adjustments(self):
        return self.db.execute_query(
            "SELECT player_id, admin_id, amount, reason FROM score_adjustments"
        )

    def test_recalculate_scores_success(self):
        self._start_day(["p1", "p2"])
        # Player 1: "800" (Wrong initially)
        # Player 2: "900" (Wrong)
        self._guess("p1", "800", "2023-01-01 10:00:00")
        self._guess("p2", "900", "2023-01-01 10:05:00")

        # Run recalculation with "800"
        result = self.game_runner.recalculate_scores_for_new_answer("800", "admin1")

        # Verify
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["updated_players"], 1)
        # 100 base + 20 first try + 10 before hint + 10 fastest = 140
        self.assertEqual(result["total_refunded"], 140)

        # Check persisted state
        self.assertEqual(
            self.data_manager.get_alternative_answers(self.question_db_id), ["800"]
        )
        self.assertEqual(self._player("p1").score, 140)
        self.assertEqual(self._player("p1").answer_streak, 1)
        self.assertEqual(self._player("p2").score, 0)
        self.assertEqual(self._player("p2").answer_streak, 0)
        self.assertEqual(
            [dict(row) for row in self._adjustments()],
            [
                {
                    "player_id": "p1",
                    "admin_id": "admin1",
                    "amount": 140,
                    "reason": "Correction for answer: 800",
                }
            ],
        )

    def test_recalculate_old_question_resolves_canonical_question_id(self):
        self._start_day(answer="A")
        self._deactivate_question()

        result = self.game_runner.recalculate_scores_for_new_answer("Alt", "admin1")

        self.assertEqual(result["status"], "success")
        # questions.id (not the daily question id) keys the alternative answers.
        self.assertNotEqual(self.question_db_id, self.daily_question_id)
        self.assertEqual(
            self.data_manager.get_alternative_answers(self.question_db_id), ["Alt"]
        )
        self.assertEqual(
            self.data_manager.get_alternative_answers(self.daily_question_id), []
        )

    def test_recalculation_consumes_newly_applied_rest_multiplier(self):
        """A correction consumes rest only when the new replay applies it."""
        self._start_day([("p1", "Player 1", 0, 0, 0.2)])
        self._guess("p1", "800")

        self.game_runner.recalculate_scores_for_new_answer("800", "admin1")

        self.assertEqual(self.data_manager.get_pending_multiplier("p1"), 0.0)

    def test_recalculate_scores_already_correct(self):
        self._start_day(["p1"])
        # Player 1: "800-899" (Correct)
        self._guess("p1", "800-899", is_correct=True)

        result = self.game_runner.recalculate_scores_for_new_answer("800", "admin1")

        self.assertEqual(result["updated_players"], 0)
        self.assertEqual(self._player("p1").score, 0)
        self.assertEqual(self._adjustments(), [])

    def test_recalculate_scores_uses_snapshot(self):
        self._start_day([("p1", "p1", 1000, 10)])
        self._guess("p1", "800")
        # Current stats drifted from the start-of-day snapshot.
        self.data_manager.update_lifetime_stats("p1", score=1234, answer_streak=10)

        result = self.game_runner.recalculate_scores_for_new_answer("800", "admin1")

        detail = result["details"][0]
        self.assertEqual(detail["score_before"], 1000)
        self.assertEqual(detail["score_after"], 1000 + result["total_refunded"])
        # Streak bonus is capped at 25, so the earned total is 100+20+10+10+25.
        self.assertEqual(result["total_refunded"], 165)
        # The correction is applied on top of the current score.
        self.assertEqual(self._player("p1").score, 1234 + 165)

    def test_recalculate_scores_falls_back_to_current_players_without_snapshot(self):
        self._start_day()  # no players yet, so nothing is snapshotted
        self.data_manager.create_player("p1", "p1")
        self.data_manager.update_lifetime_stats("p1", score=700, answer_streak=0)
        self._guess("p1", "800")

        result = self.game_runner.recalculate_scores_for_new_answer(
            "800", "admin1", dry_run=True
        )

        self.assertEqual(result["details"][0]["score_before"], 700)

    def test_recalculate_scores_dry_run(self):
        self._start_day(["p1"])
        self._guess("p1", "800")

        # Run recalculation with dry_run=True
        result = self.game_runner.recalculate_scores_for_new_answer(
            "800", "admin1", dry_run=True
        )

        # Verify results are calculated but not applied
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["updated_players"], 1)
        self.assertEqual(result["total_refunded"], 140)

        # Nothing is persisted
        self.assertEqual(
            self.data_manager.get_alternative_answers(self.question_db_id), []
        )
        self.assertEqual(self._player("p1").score, 0)
        self.assertEqual(self._player("p1").answer_streak, 0)
        self.assertEqual(self._guess_is_correct("p1"), [False])
        self.assertEqual(self._adjustments(), [])

    def test_recalculate_scores_no_active_question_uses_most_recent(self):
        """Test that recalculate uses most recent question when no active question exists."""
        self._start_day(["p1"])
        # Clear the active daily question (simulating after evening message)
        self._deactivate_question()
        self._guess("p1", "800")

        # Run recalculation
        result = self.game_runner.recalculate_scores_for_new_answer("800", "admin1")

        # Verify success against the question logged today
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["updated_players"], 1)
        self.assertEqual(
            self.data_manager.get_alternative_answers(self.question_db_id), ["800"]
        )

        # No age warning for same-day question
        self.assertEqual(result.get("age_warning"), "")

    def test_recalculate_scores_old_question_warning(self):
        """Test that recalculate warns when correcting an old question."""
        self._start_day()
        self._deactivate_question()
        two_days_ago = self.data_manager.get_today() - timedelta(days=2)
        self.db.execute_update(
            "UPDATE daily_questions SET sent_at = ?", (two_days_ago,)
        )

        # Run recalculation
        result = self.game_runner.recalculate_scores_for_new_answer("800", "admin1")

        # Verify age warning is present
        self.assertEqual(result["status"], "success")
        self.assertIn("2 day(s) old", result["age_warning"])

    def test_recalculate_scores_no_questions_exist(self):
        """Test that recalculate errors gracefully when no questions exist."""
        # No daily question was ever logged.
        result = self.game_runner.recalculate_scores_for_new_answer("800", "admin1")

        # Verify error
        self.assertEqual(result["status"], "error")
        self.assertIn("No daily question found", result["message"])
        alternatives = self.db.execute_query("SELECT * FROM alternative_answers")
        self.assertEqual(alternatives, [])

    def test_recalculate_marks_guesses_as_correct(self):
        """Test that recalculate marks previously incorrect guesses as correct in DB."""
        self._start_day(["p1", "p2"])
        # p1 guessed "800" (initially wrong), p2 guessed "900" (wrong)
        self._guess("p1", "800", "2023-01-01 10:00:00")
        self._guess("p2", "900", "2023-01-01 10:05:00")

        # Run recalculation with "800" (dry_run=False)
        self.game_runner.recalculate_scores_for_new_answer(
            "800", "admin1", dry_run=False
        )

        # Verify the alternative answer was added and only the matching guess flipped
        self.assertEqual(
            self.data_manager.get_alternative_answers(self.question_db_id), ["800"]
        )
        self.assertEqual(self._guess_is_correct("p1"), [True])
        self.assertEqual(self._guess_is_correct("p2"), [False])

    def test_details_badges_only_show_newly_gained_bonuses(self):
        """Badges in details should only reflect bonuses gained due to the new answer,
        not bonuses the player already had from the original correct answer."""
        self._start_day(["p1", "p2"])
        # p1: already correct on first try (gains first_try + before_hint from old answers)
        # p2: newly correct on first try (gains first_try + before_hint only after new answer)
        # No hint was sent, so both answers are before the hint.
        self._guess("p1", "800-899", "2023-01-01 10:00:00", is_correct=True)
        self._guess("p2", "800", "2023-01-01 10:05:00")

        result = self.game_runner.recalculate_scores_for_new_answer(
            "800", "admin1", dry_run=True
        )

        self.assertEqual(result["status"], "success")

        # Only p2 should appear in details (p1 has no score diff)
        self.assertEqual(result["updated_players"], 1)
        detail = result["details"][0]
        self.assertEqual(detail["name"], "p2")

        # p2 newly gained first_try and before_hint bonuses — both badges should appear
        self.assertIn("🎯", detail["badges"])  # JBOT_EMOJI_FIRST_TRY
        self.assertIn("🧠", detail["badges"])  # JBOT_EMOJI_BEFORE_HINT

        # p1 already had those bonuses from the original correct answer — not in details at all
        p1_details = [d for d in result["details"] if d["name"] == "p1"]
        self.assertEqual(p1_details, [])

    def test_details_badges_exclude_pre_existing_bonuses(self):
        """If a player was already correct (e.g. on a 2nd try) and the new answer doesn't
        change their bonuses, their badges list should be empty."""
        self._start_day(["p1", "p2"])
        # p1 already answered correctly on 2nd try (no first_try bonus).
        # Adding "800" as alt doesn't affect p1 at all.
        self._guess("p1", "wrong", "2023-01-01 10:00:00")
        self._guess("p1", "800-899", "2023-01-01 10:01:00", is_correct=True)
        self._guess("p2", "800", "2023-01-01 10:02:00")  # newly accepted

        result = self.game_runner.recalculate_scores_for_new_answer(
            "800", "admin1", dry_run=True
        )

        self.assertEqual(result["status"], "success")

        # p1 unchanged — not in details
        p1_details = [d for d in result["details"] if d["name"] == "p1"]
        self.assertEqual(p1_details, [])

        # p2 newly correct on first try — badges should reflect that
        p2_detail = next(d for d in result["details"] if d["name"] == "p2")
        self.assertIn("🎯", p2_detail["badges"])  # first_try
        # p2 answered after p1 (who was fastest), so no fastest badge
        self.assertNotIn("🥇", p2_detail["badges"])

    # ------------------------------------------------------------------
    # user_id in details
    # ------------------------------------------------------------------

    def test_details_include_user_id(self):
        """Each entry in details must carry the player's user_id for Discord mentioning."""
        self._start_day(["p1"])
        self._guess("p1", "800")

        result = self.game_runner.recalculate_scores_for_new_answer(
            "800", "admin1", dry_run=True
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["details"]), 1)
        self.assertIn("user_id", result["details"][0])
        self.assertEqual(result["details"][0]["user_id"], "p1")

    # ------------------------------------------------------------------
    # rest_cleared_players
    # ------------------------------------------------------------------

    def _setup_resting_player_guess(self, guess_text="new_ans"):
        """Seed a player who rested and then guessed the (possibly new) answer."""
        self._start_day([("p_rest", "RestPlayer")])
        # rest powerup fired before the guess
        self._rest("p_rest", "2023-01-01 09:00:00")
        self._guess("p_rest", guess_text, "2023-01-01 10:05:00")

    def test_rest_cleared_player_detected(self):
        """A resting player whose guess matches the new answer appears in rest_cleared_players."""
        self._setup_resting_player_guess("new_ans")

        result = self.game_runner.recalculate_scores_for_new_answer(
            "new_ans", "admin1", dry_run=True
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["rest_cleared_players"]), 1)
        cleared = result["rest_cleared_players"][0]
        self.assertEqual(cleared["user_id"], "p_rest")
        self.assertEqual(cleared["name"], "RestPlayer")

    def test_rest_cleared_clears_multiplier_when_applied(self):
        """apply=True: the pending multiplier is cleared for each rest-cleared player."""
        self._setup_resting_player_guess("new_ans")
        self.assertEqual(self.data_manager.get_pending_multiplier("p_rest"), 0.2)

        self.game_runner.recalculate_scores_for_new_answer(
            "new_ans", "admin1", dry_run=False
        )

        self.assertEqual(self.data_manager.get_pending_multiplier("p_rest"), 0.0)

    def test_rest_cleared_no_db_call_when_dry_run(self):
        """dry_run=True: rest is detected but the pending multiplier is NOT cleared."""
        self._setup_resting_player_guess("new_ans")

        result = self.game_runner.recalculate_scores_for_new_answer(
            "new_ans", "admin1", dry_run=True
        )

        self.assertEqual(len(result["rest_cleared_players"]), 1)
        self.assertEqual(self.data_manager.get_pending_multiplier("p_rest"), 0.2)

    def test_rest_cleared_only_for_matching_guess(self):
        """A resting player whose guess does NOT match the new answer is not cleared."""
        self._setup_resting_player_guess("wrong_guess")

        result = self.game_runner.recalculate_scores_for_new_answer(
            "new_ans", "admin1", dry_run=True
        )

        self.assertEqual(result["rest_cleared_players"], [])

    # ------------------------------------------------------------------
    # Regression: multiple guesses by one player — first guess upgraded
    # ------------------------------------------------------------------

    def test_first_guess_bonus_when_new_alt_matches_multiple_guesses(self):
        """
        Regression: When the new alt answer matches MORE THAN ONE of a single
        player's guesses (e.g. 'world war 1' matches both the literal guess
        'world war 1' AND 'world war one' via the 'one'→'1' normalization),
        the player should be scored on their FIRST guess (guesses_count=1)
        and receive the first-try / first_try bonus — not a 2nd-try bonus.

        Scenario
        --------
        Canonical answer : "world war i"   (neither guess matches)
        New alt answer   : "world war 1"
        Player guesses (in order):
          1. "world war 1"   — wrong live, now matches new alt directly
          2. "world war one" — wrong live, now matches new alt via normalization

        OLD sim  → both guesses wrong → score_earned = 0
        NEW sim  → guess 1 correct, guesses_count=1 → full first-try score
        score_diff = full_first_try_score  ✓
        """
        self._start_day(["p1"], answer="world war i")
        self._guess("p1", "world war 1", "2024-01-01 10:00:00")
        self._guess("p1", "world war one", "2024-01-01 10:01:00")

        result = self.game_runner.recalculate_scores_for_new_answer(
            "world war 1", "admin1", dry_run=True
        )

        self.assertEqual(result["status"], "success")
        # Exactly one player affected
        self.assertEqual(result["updated_players"], 1)
        # Score should include first-try bonus (20) + before_hint (10) + fastest_1 (10) + base (100)
        self.assertEqual(result["total_refunded"], 140)
        # 🎯 badge must be present (first_try bonus gained)
        self.assertIn("🎯", result["details"][0]["badges"])

    def test_first_guess_bonus_not_blocked_by_normalisation_equivalent_existing_alt(
        self,
    ):
        """
        Edge-case: if an existing alt is the written-out equivalent of the new
        alt (e.g. existing alt = "world war one", new alt = "world war 1"), they
        normalise to the same string.  In the OLD sim the player's first guess
        'world war 1' already matches the existing alt → old score_earned > 0.
        The diff is therefore SMALLER than a full first-try award.

        This test documents the correct, expected behaviour: the player was
        already credited by the earlier add_answer call so the diff is 0 here.
        (If the earlier call never ran, the player should have gotten the bonus
        then — this second call is a no-op from a scoring perspective.)
        """
        self._start_day(["p1"], answer="world war i")
        self._guess("p1", "world war 1", "2024-01-01 10:00:00")
        self._guess("p1", "world war one", "2024-01-01 10:01:00")
        # Existing alt "world war one" normalises to "world war 1" — same as new alt
        self.data_manager.add_alternative_answer(
            self.question_db_id, "world war one", "admin0"
        )

        result = self.game_runner.recalculate_scores_for_new_answer(
            "world war 1", "admin1", dry_run=True
        )

        self.assertEqual(result["status"], "success")
        # OLD sim already gives the player first-try via the existing "world war one"
        # alt, so NEW sim produces the same score → diff = 0 → no update needed.
        self.assertEqual(result["updated_players"], 0)

    def test_streak_not_inflated_for_newly_correct_player_on_active_question(self):
        """
        Regression: When add_answer is called while the question is still active,
        a newly-correct player's streak should be incremented by exactly 1.

        With apply_end_of_day=True (old behaviour):
          - old sim: player wrong, end_of_day resets streak → streak_delta = -N
          - new sim: player correct → streak_delta = +1
          - diff = 1 - (-N) = N+1  ← WRONG: streak over-credited by N

        With apply_end_of_day=False (fixed):
          - old sim: player wrong, no reset → streak_delta = 0
          - new sim: player correct → streak_delta = +1
          - diff = 1 ← CORRECT
        """
        # Player p1 has a 5-day streak and guesses an answer that only matches
        # the new alt answer (not the primary). Game is still active (daily_question_id matches).
        self._start_day([("p1", "P1", 500, 5)])
        self._guess("p1", "alt_answer")

        result = self.game_runner.recalculate_scores_for_new_answer(
            "alt_answer", "admin1"
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["updated_players"], 1)

        # streak_diff must be exactly +1, so the streak goes 5 -> 6
        self.assertEqual(self._player("p1").answer_streak, 6)

    def test_streak_unchanged_for_non_answering_player_on_active_question(self):
        """
        Regression: A player who didn't answer should have streak_diff=0 even when
        add_answer is called mid-day (apply_end_of_day would otherwise reset them
        in both sims and cancel out correctly, but this verifies they're excluded).
        """
        self._start_day([("p1", "P1", 500, 3), ("p2", "P2", 1000, 7)])

        # Only p1 answers (newly correct); p2 doesn't answer at all
        self._guess("p1", "alt_answer")

        result = self.game_runner.recalculate_scores_for_new_answer(
            "alt_answer", "admin1"
        )

        # p2 should NOT appear in details (no score diff, no streak diff)
        p2_in_details = any(d["user_id"] == "p2" for d in result.get("details", []))
        self.assertFalse(
            p2_in_details,
            "p2 did not answer and should not appear in score adjustment details",
        )
        # Only p1's persisted state changes
        self.assertEqual(self._player("p1").answer_streak, 4)
        self.assertEqual(self._player("p2").answer_streak, 7)
        self.assertEqual(self._player("p2").score, 1000)
        self.assertEqual({row["player_id"] for row in self._adjustments()}, {"p1"})
