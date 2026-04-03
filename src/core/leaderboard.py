"""
Leaderboard rendering for the daily trivia game.

LeaderboardRow is the data contract between GameRunner (assembly) and
LeaderboardRenderer (display).  Nothing outside these two classes should
construct rows or format strings for the leaderboard.
"""

from dataclasses import dataclass, field

# Discord renders most game emoji at 2 display-character widths.
EMOJI_DISPLAY_WIDTH = 2


@dataclass
class LeaderboardRow:
    display_name: str
    score: int
    streak: int = 0  # 0 → blank column
    broken_streak: int = (
        0  # >0 → show broken-streak emoji; only populated on evening leaderboard
    )
    badges: str = ""  # pre-joined emoji string; "" → no badges column entry


class LeaderboardRenderer:
    """
    Stateless renderer that converts a sorted list of LeaderboardRow objects
    into a Discord-ready monospaced code-block string.

    Rules:
    - Caller is responsible for sorting rows (score desc).
    - Tied rows share the same rank number; rank+score columns are blanked for
      subsequent tied rows (compactness).
    - Streak column shows the raw number; fire emoji is the column *header* only.
    - Emoji assumed to be EMOJI_DISPLAY_WIDTH display chars for alignment.
    """

    MAX_NAME_WIDTH = 16

    def render(
        self,
        rows: list[LeaderboardRow],
        show_badges: bool = False,
        streak_emoji: str = "🔥",
        broken_streak_emoji: str = "💔",
    ) -> str:
        if not rows:
            return "No scores available yet."

        # --- column widths ---
        name_width = min(self.MAX_NAME_WIDTH, max(len(r.display_name) for r in rows))
        name_width = max(name_width, len("Player"))

        score_width = max(len("pts"), max(len(str(r.score)) for r in rows))

        streak_digits = max(
            (len(str(r.streak)) for r in rows if r.streak > 0),
            default=0,
        )
        has_broken = any(r.broken_streak > 0 for r in rows)
        streak_width = max(
            EMOJI_DISPLAY_WIDTH,
            streak_digits,
            EMOJI_DISPLAY_WIDTH if has_broken else 0,
        )

        # --- header ---
        # Right-align the streak emoji header within the streak column width.
        streak_head = " " * max(0, streak_width - EMOJI_DISPLAY_WIDTH) + streak_emoji
        header = f"🏆 {'Player':<{name_width}} {'pts':>{score_width}} {streak_head}"
        if show_badges:
            header += " Badges"

        # --- separator ---
        sep = f"-- {'-' * name_width} {'-' * score_width} {'-' * streak_width}"
        if show_badges:
            sep += " ----------"

        # --- body ---
        lines = []
        rank = 0
        last_score = None
        for i, row in enumerate(rows):
            if row.score != last_score:
                rank = i + 1
                last_score = row.score

            name = row.display_name[:name_width]

            if row.streak > 0:
                streak_str = f"{row.streak:>{streak_width}}"
            elif row.broken_streak > 0:
                pad = max(0, streak_width - EMOJI_DISPLAY_WIDTH)
                streak_str = " " * pad + broken_streak_emoji
            else:
                streak_str = " " * streak_width

            is_tied = i > 0 and row.score == rows[i - 1].score
            if is_tied:
                line = f"{'':>2} {name:<{name_width}} {'':>{score_width}} {streak_str}"
            else:
                line = f"{rank:>2} {name:<{name_width}} {row.score:>{score_width}} {streak_str}"

            if show_badges:
                line += f" {row.badges}"

            lines.append(line)

        body = "\n".join(lines)
        return f"```{header}\n{sep}\n{body}\n```"
