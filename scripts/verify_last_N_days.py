"""
Offline script to run verify_daily_play against the last 7 days of real DB data.

NOTE: this displays per-day diffs, but in practice a diff from the past may change
later diffs (e.g. if a streak is increased 3d ago, that may cause a later day's jinx
steal to earn more points than it did in the real play). The generated SQL fixes are
based on the isolated diffs for each day, so they may not be perfectly
self-consistent if multiple days have discrepancies. Use the per-day diffs and player
summary to understand the issues before applying any fixes, and verify current DB
values before applying the generated SQL.

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
import io
import builtins
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


def get_next_day_snapshot(
    data_manager: DataManager, current_dq_id: int
) -> tuple[dict | None, int | None]:
    """
    Find the next daily_question_id after current_dq_id and return its
    snapshot and that ID. Returns (None, None) if not found.
    """
    rows = data_manager._db.execute_query(
        "SELECT id FROM daily_questions WHERE id > ? ORDER BY id ASC LIMIT 1",
        (current_dq_id,),
    )
    if not rows:
        return None, None
    next_dq_id = rows[0]["id"]
    return data_manager.get_daily_snapshot(next_dq_id), next_dq_id


def verify_day_retrospective(
    data_manager: DataManager,
    config: ConfigReader,
    daily_question_id: int,
    actual_players: dict,
) -> tuple[list[dict], int | None]:
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

    return diffs, season_id


def format_fix_sql(all_fix_data: list[dict]) -> str:
    """
    Given a list of fix records collected during verification, emit SQL UPDATE
    statements to bring the DB in line with simulator expectations.

    Each record has:
      sent_at, dq_id, snapshot_dq_id (None if live), is_live, season_id, diffs
    """
    lines = []
    lines.append("\n" + "=" * 60)
    lines.append("SUGGESTED DB EDITS (review before applying)")
    lines.append("=" * 60)

    for fix in all_fix_data:
        sent_at = fix["sent_at"]
        dq_id = fix["dq_id"]
        snapshot_dq_id = fix["snapshot_dq_id"]
        season_id = fix["season_id"]
        is_live = fix["is_live"]
        diffs = fix["diffs"]

        if not diffs:
            continue

        if not is_live:
            lines.append(
                f"\n-- Day {sent_at} (dq={dq_id}): "
                f"fix daily_player_states snapshot dq={snapshot_dq_id}"
            )
            for entry in sorted(diffs, key=lambda e: e["player_name"].lower()):
                pid = entry["player_id"]
                name = entry["player_name"]
                for field, vals in entry["diffs"].items():
                    exp = vals["expected"]
                    act = vals["actual"]
                    delta = exp - act
                    col = {
                        "score": "score",
                        "season_score": "season_points",
                        "streak": "answer_streak",
                    }.get(field)
                    if col:
                        lines.append(
                            f"UPDATE daily_player_states"
                            f" SET {col} = {exp}"
                            f" WHERE daily_question_id = {snapshot_dq_id}"
                            f" AND player_id = '{pid}';"
                            f"  -- {name}: {act} -> {exp} ({delta:+})"
                        )
        else:
            lines.append(
                f"\n-- Day {sent_at} (dq={dq_id}): fix current players/season_scores"
            )
            for entry in sorted(diffs, key=lambda e: e["player_name"].lower()):
                pid = entry["player_id"]
                name = entry["player_name"]
                for field, vals in entry["diffs"].items():
                    exp = vals["expected"]
                    act = vals["actual"]
                    delta = exp - act
                    if field == "score":
                        lines.append(
                            f"UPDATE players SET score = {exp} WHERE id = '{pid}';"
                            f"  -- {name}: {act} -> {exp} ({delta:+})"
                        )
                    elif field == "season_score":
                        lines.append(
                            f"UPDATE players SET season_score = {exp} WHERE id = '{pid}';"
                            f"  -- {name}: {act} -> {exp} ({delta:+})"
                        )
                        if season_id is not None:
                            lines.append(
                                f"UPDATE season_scores SET points = {exp}"
                                f" WHERE player_id = '{pid}' AND season_id = {season_id};"
                                f"  -- {name}"
                            )
                    elif field == "streak":
                        lines.append(
                            f"UPDATE players SET answer_streak = {exp} WHERE id = '{pid}';"
                            f"  -- {name}: {act} -> {exp}"
                        )

    return "\n".join(lines)


def format_player_summary(all_fix_data: list[dict]) -> str:
    """
    Aggregate discrepancies by player across all days and suggest corrections
    for the live ``players`` / ``season_scores`` tables.

    For score and season_score, the net correction is the sum of
    (expected - actual) across all snapshot days: each day's delta represents
    an isolated error introduced by that day's real-time game execution, so
    they accumulate independently in the live DB.

    Streak discrepancies in historical snapshots are shown for information only
    -- streaks are path-dependent and the current value is already corrected by
    the live-day block above when applicable.

    NOTE: This assumes no manual DB corrections were applied between the days
    shown. Verify current values before applying the generated SQL.
    """
    player_info: dict[str, dict] = {}

    for fix in all_fix_data:
        sent_at = fix["sent_at"]
        is_live = fix["is_live"]
        season_id = fix["season_id"]

        for entry in fix["diffs"]:
            pid = entry["player_id"]
            name = entry["player_name"]

            if pid not in player_info:
                player_info[pid] = {
                    "name": name,
                    "season_id": None,
                    # (sent_at, field, actual, expected, delta, is_live)
                    "entries": [],
                    # cumulative delta from snapshot days only
                    "net": {},
                }

            if season_id:
                player_info[pid]["season_id"] = season_id

            for field, vals in entry["diffs"].items():
                delta = vals["expected"] - vals["actual"]
                player_info[pid]["entries"].append(
                    (sent_at, field, vals["actual"], vals["expected"], delta, is_live)
                )
                if not is_live:
                    player_info[pid]["net"][field] = (
                        player_info[pid]["net"].get(field, 0) + delta
                    )

    if not player_info:
        return ""

    lines: list[str] = []
    lines.append("\n" + "=" * 60)
    lines.append("PLAYER CHANGE SUMMARY")
    lines.append("=" * 60)

    for pid, data in sorted(player_info.items(), key=lambda x: x[1]["name"].lower()):
        lines.append(f"\n{data['name']} ({pid})")
        for sent_at, field, actual, expected, delta, is_live in sorted(data["entries"]):
            flag = "  [live]" if is_live else ""
            lines.append(
                f"  {sent_at}  {field:<14}  {actual:>8} -> {expected:>8}  ({delta:+}){flag}"
            )
        nonzero_net = {f: d for f, d in data["net"].items() if d != 0}
        if nonzero_net:
            parts = ", ".join(f"{f}: {d:+}" for f, d in sorted(nonzero_net.items()))
            lines.append(f"  NET (snapshot days): {parts}")

    # SQL corrections for the live players / season_scores tables.
    # Live-day corrections are already emitted in the SUGGESTED DB EDITS block;
    # here we only emit delta-based corrections derived from snapshot days.
    sql_lines: list[str] = []
    for pid, data in sorted(player_info.items(), key=lambda x: x[1]["name"].lower()):
        name = data["name"]
        season_id = data["season_id"]
        net = data["net"]

        score_delta = net.get("score", 0)
        if score_delta != 0:
            sql_lines.append(
                f"UPDATE players SET score = score + ({score_delta})"
                f" WHERE id = '{pid}';  -- {name} ({score_delta:+})"
            )

        season_delta = net.get("season_score", 0)
        if season_delta != 0:
            sql_lines.append(
                f"UPDATE players SET season_score = season_score + ({season_delta})"
                f" WHERE id = '{pid}';  -- {name} ({season_delta:+})"
            )
            if season_id is not None:
                sql_lines.append(
                    f"UPDATE season_scores SET points = points + ({season_delta})"
                    f" WHERE player_id = '{pid}' AND season_id = {season_id};"
                    f"  -- {name}"
                )

    if sql_lines:
        lines.append("\n" + "-" * 60)
        lines.append("SUGGESTED LIVE TABLE CORRECTIONS (players / season_scores)")
        lines.append(
            "Cumulative net delta across all snapshot days. "
            "Assumes no manual corrections applied between days."
        )
        lines.append("Verify current DB values before applying.")
        lines.append("-" * 60)
        lines.extend(sql_lines)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Verify daily play for recent days")
    parser.add_argument(
        "--days", type=int, default=7, help="Number of days to look back (default: 7)"
    )
    parser.add_argument(
        "--db", type=str, default="jbot.db", help="Path to SQLite database"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="verify_output.txt",
        help="Write full output to this file (default: verify_output.txt)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    output_path = os.path.abspath(args.output)

    buffer = io.StringIO()

    def print(*args, **kwargs):
        builtins.print(*args, **kwargs)
        kwargs.pop("file", None)
        builtins.print(*args, file=buffer, **kwargs)

    db = Database(args.db)
    data_manager = DataManager(db)
    config = ConfigReader()

    rows = get_recent_daily_questions(db, args.days)
    if not rows:
        print(f"No daily questions found in the last {args.days} day(s).")
        return

    print(f"Verifying {len(rows)} day(s) of play (last {args.days} days)...\n")

    all_clean = True
    all_fix_data = []

    for i, row in enumerate(rows):
        dq_id = row["daily_question_id"]
        sent_at = row["sent_at"]
        is_last = i == len(rows) - 1

        # For past days, use the next day's snapshot as end-of-day actuals.
        # For the most recent day (today), fall back to live player state.
        next_snapshot, next_dq_id = get_next_day_snapshot(data_manager, dq_id)

        if next_snapshot:
            source = "next-day snapshot"
            diffs, season_id = verify_day_retrospective(
                data_manager, config, dq_id, next_snapshot
            )
            if diffs:
                all_fix_data.append(
                    {
                        "sent_at": sent_at,
                        "dq_id": dq_id,
                        "snapshot_dq_id": next_dq_id,
                        "is_live": False,
                        "season_id": season_id,
                        "diffs": diffs,
                    }
                )
        elif is_last:
            source = "live player state"
            # Build a GameRunner for live comparison (today's in-progress game)
            selector = QuestionSelector(sources=[], questions=[])
            runner = GameRunner(selector, data_manager)
            diffs = runner.verify_daily_play(dq_id)
            if diffs:
                season_id = data_manager.get_snapshot_season_id(dq_id)
                all_fix_data.append(
                    {
                        "sent_at": sent_at,
                        "dq_id": dq_id,
                        "snapshot_dq_id": None,
                        "is_live": True,
                        "season_id": season_id,
                        "diffs": diffs,
                    }
                )
        else:
            print(f"--- Day: {sent_at}  (id={dq_id}) ---")
            print("  SKIP — no next-day snapshot available")
            print()
            continue

        print(f"--- Day: {sent_at}  (id={dq_id}, using {source}) ---")

        if diffs:
            all_clean = False
            sorted_diffs = sorted(diffs, key=lambda e: e["player_name"].lower())
            report = GameRunner.format_verify_report(dq_id, sorted_diffs)
            report = report.replace("**", "").replace("⚠️ ", "")
            print(report)
        else:
            print("  OK — no discrepancies")
        print()

    if all_clean:
        print("All days verified clean.")
    else:
        print("Discrepancies detected — see above.")

    if all_fix_data:
        print(format_fix_sql(all_fix_data))
        summary = format_player_summary(all_fix_data)
        if summary:
            print(summary)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(buffer.getvalue())
    builtins.print(f"\nOutput written to: {output_path}")


if __name__ == "__main__":
    main()
