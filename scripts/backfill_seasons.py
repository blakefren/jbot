"""
Historical Season Analysis Tool

Analyzes existing daily_questions and guesses data to generate hypothetical
season reports. Shows who would have won each month and provides competitive
balance metrics to validate the season concept.

Usage:
    python scripts/backfill_seasons.py --dry-run  # Analysis only (recommended first)
    python scripts/backfill_seasons.py --populate  # Actually populate seasons tables
"""

import sqlite3
import os
import sys
from datetime import datetime, date
from collections import defaultdict
from typing import Dict, List, Tuple
import argparse

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.database import Database


class SeasonAnalyzer:
    """Analyzes historical game data to simulate monthly seasons."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def get_all_daily_questions(self) -> List[Dict]:
        """Get all historical daily questions with their dates."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, question_id, sent_at
            FROM daily_questions
            ORDER BY sent_at ASC
        """)
        return [dict(row) for row in cursor.fetchall()]

    def get_guesses_for_question(self, daily_question_id: int) -> List[Dict]:
        """Get all guesses for a specific daily question."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT
                player_id,
                is_correct,
                guessed_at
            FROM guesses
            WHERE daily_question_id = ?
            ORDER BY guessed_at ASC
        """,
            (daily_question_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_player_name(self, player_id: str) -> str:
        """Get player's display name."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM players WHERE id = ?", (player_id,))
        result = cursor.fetchone()
        return result["name"] if result else f"Unknown ({player_id})"

    def calculate_question_points(
        self, guesses: List[Dict], daily_question_id: int
    ) -> Dict[str, int]:
        """
        Calculate points earned by each player for a specific question.
        Uses simplified scoring: correct = 100 pts, first correct = +50 pts.
        (Real scoring uses streak bonuses, but we'll keep this simple for analysis)
        """
        points = defaultdict(int)
        first_correct_awarded = False

        for guess in guesses:
            if guess["is_correct"]:
                player_id = guess["player_id"]
                points[player_id] = 100  # Base points for correct answer

                if not first_correct_awarded:
                    points[player_id] += 50  # First answer bonus
                    first_correct_awarded = True

        return dict(points)

    def group_questions_by_month(
        self, daily_questions: List[Dict]
    ) -> Dict[str, List[Dict]]:
        """Group questions by calendar month (YYYY-MM)."""
        months = defaultdict(list)

        for dq in daily_questions:
            sent_at = dq["sent_at"]
            # Parse date (format: YYYY-MM-DD)
            try:
                dt = datetime.fromisoformat(sent_at.replace(" ", "T"))
                month_key = dt.strftime("%Y-%m")  # e.g., "2025-12"
                months[month_key].append(dq)
            except Exception as e:
                print(f"Warning: Could not parse date {sent_at}: {e}")
                continue

        return dict(months)

    def analyze_season(self, month_key: str, questions: List[Dict]) -> Dict[str, any]:
        """Analyze a single season (month) and return stats."""
        season_scores = defaultdict(int)
        season_correct_counts = defaultdict(int)
        total_questions = len(questions)

        for dq in questions:
            guesses = self.get_guesses_for_question(dq["id"])
            points = self.calculate_question_points(guesses, dq["id"])

            for player_id, pts in points.items():
                season_scores[player_id] += pts
                season_correct_counts[player_id] += 1

        # Sort by score
        rankings = sorted(season_scores.items(), key=lambda x: x[1], reverse=True)

        return {
            "month": month_key,
            "total_questions": total_questions,
            "total_players": len(season_scores),
            "rankings": rankings,
            "correct_counts": dict(season_correct_counts),
        }

    def generate_report(self) -> str:
        """Generate a comprehensive analysis report."""
        print("Analyzing historical data...")

        daily_questions = self.get_all_daily_questions()
        if not daily_questions:
            return "No historical data found."

        months = self.group_questions_by_month(daily_questions)
        print(f"Found {len(months)} months of data\n")

        # Filter out incomplete months (need at least ~20 questions for valid season)
        MIN_QUESTIONS_PER_SEASON = 20
        valid_months = {
            month_key: questions
            for month_key, questions in months.items()
            if len(questions) >= MIN_QUESTIONS_PER_SEASON
        }

        excluded_count = len(months) - len(valid_months)
        if excluded_count > 0:
            print(
                f"Excluding {excluded_count} month(s) with fewer than {MIN_QUESTIONS_PER_SEASON} questions\n"
            )

        if not valid_months:
            return "No valid season data found (all months had too few questions)."

        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("HISTORICAL SEASON ANALYSIS")
        report_lines.append("=" * 80)
        report_lines.append("")

        all_winners = []
        all_score_gaps = []

        for month_key in sorted(valid_months.keys()):
            questions = months[month_key]
            analysis = self.analyze_season(month_key, questions)

            # Month header
            dt = datetime.strptime(month_key, "%Y-%m")
            month_name = dt.strftime("%B %Y")
            report_lines.append(f"📅 {month_name}")
            report_lines.append(f"   Questions: {analysis['total_questions']}")
            report_lines.append(f"   Players: {analysis['total_players']}")
            report_lines.append("")

            # Top 5 rankings
            report_lines.append("   Leaderboard:")
            prev_score = None
            current_rank = 1
            for i, (player_id, score) in enumerate(analysis["rankings"][:5], 0):
                player_name = self.get_player_name(player_id)
                correct = analysis["correct_counts"][player_id]

                # Handle ties - same score = same rank
                if prev_score is not None and score < prev_score:
                    current_rank = i + 1

                trophy = ""
                if current_rank == 1:
                    trophy = "🥇"
                    all_winners.append(player_name)
                elif current_rank == 2:
                    trophy = "🥈"
                elif current_rank == 3:
                    trophy = "🥉"

                report_lines.append(
                    f"      {trophy} {current_rank}. {player_name}: {score} pts ({correct}/{analysis['total_questions']} correct)"
                )

                prev_score = score

            # Score gap analysis (1st to 2nd place)
            if len(analysis["rankings"]) >= 2:
                first_score = analysis["rankings"][0][1]
                second_score = analysis["rankings"][1][1]
                gap = first_score - second_score
                all_score_gaps.append(gap)
                report_lines.append(f"   Gap (1st-2nd): {gap} points")

            report_lines.append("")

        # Summary statistics
        report_lines.append("=" * 80)
        report_lines.append("SUMMARY STATISTICS")
        report_lines.append("=" * 80)
        report_lines.append("")

        # Most wins
        if all_winners:
            winner_counts = defaultdict(int)
            for winner in all_winners:
                winner_counts[winner] += 1

            report_lines.append("Trophy Case (Most Season Wins):")
            for player, wins in sorted(
                winner_counts.items(), key=lambda x: x[1], reverse=True
            )[:5]:
                report_lines.append(f"   🏆 {player}: {wins} wins")
            report_lines.append("")

        # Competitive balance
        if all_score_gaps:
            avg_gap = sum(all_score_gaps) / len(all_score_gaps)
            min_gap = min(all_score_gaps)
            max_gap = max(all_score_gaps)

            report_lines.append("Competitive Balance (1st-2nd Place Gaps):")
            report_lines.append(f"   Average: {avg_gap:.0f} points")
            report_lines.append(f"   Minimum: {min_gap} points (closest race)")
            report_lines.append(f"   Maximum: {max_gap} points (biggest blowout)")
            report_lines.append("")

            # Analysis
            if avg_gap < 200:
                report_lines.append(
                    "   ✅ Seasons look competitive - small average gap suggests close races"
                )
            elif avg_gap < 400:
                report_lines.append(
                    "   ⚠️  Moderate competitiveness - some months may be runaways"
                )
            else:
                report_lines.append(
                    "   ⚠️  Low competitiveness - consider if seasons will improve engagement"
                )

        report_lines.append("")
        report_lines.append("=" * 80)

        return "\n".join(report_lines)

    def populate_seasons_tables(self):
        """
        Populate the seasons and season_scores tables with historical data.
        WARNING: Only run this after schema migration is complete!
        """
        print("WARNING: This will populate the seasons tables with historical data.")
        print("Make sure you have run the schema migration first!")

        confirm = input("Continue? (yes/no): ")
        if confirm.lower() != "yes":
            print("Aborted.")
            return

        daily_questions = self.get_all_daily_questions()
        months = self.group_questions_by_month(daily_questions)

        # Filter out incomplete months
        MIN_QUESTIONS_PER_SEASON = 20
        valid_months = {
            month_key: questions
            for month_key, questions in months.items()
            if len(questions) >= MIN_QUESTIONS_PER_SEASON
        }

        cursor = self.conn.cursor()

        for month_key in sorted(valid_months.keys()):
            questions = valid_months[month_key]
            analysis = self.analyze_season(month_key, questions)

            # Create season record
            dt = datetime.strptime(month_key, "%Y-%m")
            month_name = dt.strftime("%B %Y")

            # Calculate start and end dates
            first_question_date = questions[0]["sent_at"].split(" ")[0]
            last_question_date = questions[-1]["sent_at"].split(" ")[0]

            try:
                cursor.execute(
                    """
                    INSERT INTO seasons (season_name, start_date, end_date, is_active)
                    VALUES (?, ?, ?, 0)
                """,
                    (month_name, first_question_date, last_question_date),
                )
                season_id = cursor.lastrowid

                # Populate season_scores for each player with proper tie handling
                prev_score = None
                current_rank = 1
                for i, (player_id, score) in enumerate(analysis["rankings"]):
                    # Handle ties - same score = same rank
                    if prev_score is not None and score < prev_score:
                        current_rank = i + 1

                    trophy = None
                    if current_rank == 1:
                        trophy = "gold"
                    elif current_rank == 2:
                        trophy = "silver"
                    elif current_rank == 3:
                        trophy = "bronze"

                    cursor.execute(
                        """
                        INSERT INTO season_scores
                        (player_id, season_id, points, questions_answered, correct_answers, final_rank, trophy)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            player_id,
                            season_id,
                            score,
                            analysis["total_questions"],
                            analysis["correct_counts"][player_id],
                            current_rank,
                            trophy,
                        ),
                    )

                    prev_score = score

                print(f"✓ Populated {month_name}")

            except sqlite3.Error as e:
                print(f"Error populating {month_name}: {e}")
                self.conn.rollback()
                return

        self.conn.commit()
        print(f"\nSuccessfully populated {len(valid_months)} seasons!")
        if len(valid_months) < len(months):
            print(
                f"(Excluded {len(months) - len(valid_months)} month(s) with fewer than {MIN_QUESTIONS_PER_SEASON} questions)"
            )

    def close(self):
        """Close database connection."""
        self.conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Analyze historical data for season implementation"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate analysis report only (default)",
    )
    parser.add_argument(
        "--populate",
        action="store_true",
        help="Actually populate seasons tables (run after schema migration)",
    )

    args = parser.parse_args()

    # Database path - db/jbot.db in project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)  # Go up from scripts/ to root
    db_path = os.path.join(project_root, "db", "jbot.db")

    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        print(f"Expected location: {db_path}")
        print(f"Project root: {project_root}")
        print("\nMake sure:")
        print("  1. The bot has been run at least once to create db/jbot.db")
        print(
            "  2. You're running this script from the project root or scripts directory"
        )
        sys.exit(1)

    analyzer = SeasonAnalyzer(db_path)

    try:
        if args.populate:
            analyzer.populate_seasons_tables()
        else:
            # Default: dry run
            report = analyzer.generate_report()
            print(report)

            # Save to file
            report_path = os.path.join(
                os.path.dirname(__file__), "season_analysis_report.txt"
            )
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report)
            print(f"\n📄 Report saved to: {report_path}")

    finally:
        analyzer.close()


if __name__ == "__main__":
    main()
