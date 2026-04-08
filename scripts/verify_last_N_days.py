"""
Offline script to run verify_daily_play against the last 7 days of real DB data.

For past days, uses the next day's daily_player_states snapshot as the "actual"
end-of-day state (since that snapshot captures player state right before the
next morning's question). For today's question, falls back to the live
get_all_players() comparison (same as production verify_daily_play).

Usage:
    python scripts/verify_last_7d.py [--days N] [--db PATH]

Requires .env to be present (for ConfigReader / scoring config).
"""

import sys
import os
import argparse
import logging

# Ensure project root is on the path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from db.database import Database
from src.core.data_manager import DataManager
from src.core.game_runner import GameRunner
from src.core.daily_game_simulator import DailyGameSimulator
from src.core.answer_checker import AnswerChecker
from src.core.events import GuessEvent, PowerUpEvent
from src.core.utils import parse_timestamp
from src.cfg.main import ConfigReader
from data.readers.question_selector import QuestionSelector


def get_recent_daily_questions(db: Database, days: int) -> list[dict]:
    """Fetch daily_question rows from the last N days, oldest first."""
    query = """
        SELECT id AS daily_question_id, question_id, sent_at
        FROM daily_questions
        WHERE sent_at >= DATE('now', ?)
        ORDER BY sent_at ASC
    """
    return db.execute_query(query, (f"-{days} days",))


def get_next_day_snapshot(data_manager: DataManager, current_dq_id: int) -> dict | None:
    """
    Find the next daily_question_id after current_dq_id and return its
    snapshot (which represents the end-of-day state for current_dq_id's day).
    """
    rows = data_manager._db.execute_query(
        "SELECT id FROM daily_questions WHERE id > ? ORDER BY id ASC LIMIT 1",
        (current_dq_id,),
    )
    if not rows:
        return None
    next_dq_id = rows[0]["id"]
    return data_manager.get_daily_snapshot(next_dq_id)


def verify_day_retrospective(
    data_manager: DataManager,
    config: ConfigReader,
    daily_question_id: int,
    actual_players: dict,
) -> list[dict]:
    """
    Replay a day's events from its snapshot and compare against actual_players.
    actual_players is a dict[str, Player] representing end-of-day state.
    """
    answer_checker = AnswerChecker()

    snapshot = data_manager.get_daily_snapshot(daily_question_id)
    if not snapshot:
        return []

    question_info = data_manager.get_daily_question_by_id(daily_question_id)
    if not question_info:
        return []
    daily_q, _ = question_info

    answers = [daily_q.answer] + data_manager.get_alternative_answers(daily_question_id)
    hint_ts = data_manager.get_hint_sent_timestamp(daily_question_id)

    # Fetch events
    guesses = data_manager.get_guesses_for_daily_question(daily_question_id)
    powerups = data_manager.get_powerup_usages_for_question(daily_question_id)
    events = []
    for g in guesses:
        ts = parse_timestamp(g["guessed_at"])
        events.append(GuessEvent(ts, g["player_id"], g["guess_text"]))
    for p in powerups:
        ts = parse_timestamp(p["used_at"])
        events.append(
            PowerUpEvent(ts, p["user_id"], p["powerup_type"], p["target_user_id"])
        )

    simulator = DailyGameSimulator(
        daily_q,
        answers,
        hint_ts,
        events,
        snapshot,
        config,
        answer_checker=answer_checker,
    )
    sim_results = simulator.run(apply_end_of_day=True)

    season_id = data_manager.get_snapshot_season_id(daily_question_id)

    diffs = []
    for user_id, expected in sim_results.items():
        actual_player = actual_players.get(user_id)
        if not actual_player:
            continue

        player_diffs = {}

        if expected["final_score"] != actual_player.score:
            player_diffs["score"] = {
                "expected": expected["final_score"],
                "actual": actual_player.score,
            }

        if expected["final_streak"] != actual_player.answer_streak:
            player_diffs["streak"] = {
                "expected": expected["final_streak"],
                "actual": actual_player.answer_streak,
            }

        if season_id is not None:
            snapshot_player = snapshot.get(user_id)
            initial_season_score = (
                snapshot_player.season_score if snapshot_player else 0
            )
            expected_season_score = initial_season_score + expected["score_earned"]
            actual_season_score = actual_player.season_score
            if expected_season_score != actual_season_score:
                player_diffs["season_score"] = {
                    "expected": expected_season_score,
                    "actual": actual_season_score,
                }

        if player_diffs:
            player_name = snapshot[user_id].name if user_id in snapshot else user_id
            diffs.append(
                {
                    "player_id": user_id,
                    "player_name": player_name,
                    "diffs": player_diffs,
                }
            )

    return diffs


def main():
    parser = argparse.ArgumentParser(description="Verify daily play for recent days")
    parser.add_argument(
        "--days", type=int, default=7, help="Number of days to look back (default: 7)"
    )
    parser.add_argument(
        "--db", type=str, default="jbot.db", help="Path to SQLite database"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    db = Database(args.db)
    data_manager = DataManager(db)
    config = ConfigReader()

    rows = get_recent_daily_questions(db, args.days)
    if not rows:
        print(f"No daily questions found in the last {args.days} day(s).")
        return

    print(f"Verifying {len(rows)} day(s) of play (last {args.days} days)...\n")

    all_clean = True
    for i, row in enumerate(rows):
        dq_id = row["daily_question_id"]
        sent_at = row["sent_at"]
        is_last = i == len(rows) - 1

        # For past days, use the next day's snapshot as end-of-day actuals.
        # For the most recent day (today), fall back to live player state.
        next_snapshot = get_next_day_snapshot(data_manager, dq_id)

        if next_snapshot:
            source = "next-day snapshot"
            diffs = verify_day_retrospective(data_manager, config, dq_id, next_snapshot)
        elif is_last:
            source = "live player state"
            # Build a GameRunner for live comparison (today's in-progress game)
            selector = QuestionSelector(sources=[], questions=[])
            runner = GameRunner(selector, data_manager)
            diffs = runner.verify_daily_play(dq_id)
        else:
            print(f"--- Day: {sent_at}  (id={dq_id}) ---")
            print("  SKIP — no next-day snapshot available")
            print()
            continue

        print(f"--- Day: {sent_at}  (id={dq_id}, using {source}) ---")

        if diffs:
            all_clean = False
            report = GameRunner.format_verify_report(dq_id, diffs)
            report = report.replace("**", "").replace("⚠️ ", "")
            print(report)
        else:
            print("  OK — no discrepancies")
        print()

    if all_clean:
        print("All days verified clean.")
    else:
        print("Discrepancies detected — see above.")


if __name__ == "__main__":
    main()
