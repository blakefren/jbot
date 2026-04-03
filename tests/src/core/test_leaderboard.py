import unittest

from src.core.leaderboard import LeaderboardRenderer, LeaderboardRow


def make_renderer():
    return LeaderboardRenderer()


class TestLeaderboardRendererEmpty(unittest.TestCase):
    def test_empty_rows_returns_no_scores_message(self):
        result = make_renderer().render([])
        self.assertEqual(result, "No scores available yet.")


class TestLeaderboardRendererBasic(unittest.TestCase):
    def setUp(self):
        self.rows = [
            LeaderboardRow("Alice", 1000, streak=5),
            LeaderboardRow("Bob", 800, streak=2),
            LeaderboardRow("Charlie", 600),
        ]

    def test_output_is_code_block(self):
        result = make_renderer().render(self.rows)
        self.assertTrue(result.startswith("```"))
        self.assertTrue(result.endswith("```"))

    def test_contains_player_names(self):
        result = make_renderer().render(self.rows)
        self.assertIn("Alice", result)
        self.assertIn("Bob", result)
        self.assertIn("Charlie", result)

    def test_contains_scores(self):
        result = make_renderer().render(self.rows)
        self.assertIn("1000", result)
        self.assertIn("800", result)
        self.assertIn("600", result)

    def test_contains_header_symbols(self):
        result = make_renderer().render(self.rows)
        self.assertIn("🏆", result)
        self.assertIn("🔥", result)
        self.assertIn("Player", result)
        self.assertIn("pts", result)

    def test_no_badges_column_when_show_badges_false(self):
        result = make_renderer().render(self.rows, show_badges=False)
        self.assertNotIn("Badges", result)

    def test_badges_column_header_when_show_badges_true(self):
        rows = [LeaderboardRow("Alice", 1000, badges="🎯")]
        result = make_renderer().render(rows, show_badges=True)
        self.assertIn("Badges", result)
        self.assertIn("🎯", result)

    def test_streak_numbers_appear(self):
        result = make_renderer().render(self.rows)
        self.assertIn("5", result)
        self.assertIn("2", result)

    def test_zero_streak_is_blank_not_zero(self):
        rows = [LeaderboardRow("Alice", 100, streak=0)]
        result = make_renderer().render(rows)
        # "0" might appear in score; check it doesn't appear in streak column
        # Simplest check: no "🔥0" pattern
        self.assertNotIn("🔥0", result)


class TestLeaderboardRendererRanks(unittest.TestCase):
    def test_sequential_ranks(self):
        rows = [
            LeaderboardRow("Alice", 300),
            LeaderboardRow("Bob", 200),
            LeaderboardRow("Charlie", 100),
        ]
        result = make_renderer().render(rows)
        lines = result.strip("`").strip().splitlines()
        body_lines = [
            l for l in lines if l and l[0].isspace() or l[:2].strip().isdigit()
        ]
        # The first data row should have rank 1
        data_lines = [l for l in lines[2:] if l.strip()]  # skip header + sep
        self.assertTrue(data_lines[0].startswith(" 1"))
        self.assertTrue(data_lines[1].startswith(" 2"))
        self.assertTrue(data_lines[2].startswith(" 3"))

    def test_tied_players_share_rank(self):
        rows = [
            LeaderboardRow("Alice", 300),
            LeaderboardRow("Bob", 300),
            LeaderboardRow("Charlie", 100),
        ]
        result = make_renderer().render(rows)
        lines = [l for l in result.strip("`").strip().splitlines()]
        data_lines = [l for l in lines[2:] if l.strip()]
        # Both Alice and Bob share rank 1; Charlie is rank 3
        self.assertTrue(data_lines[0].startswith(" 1"))
        # Second tied row has blank rank column
        self.assertTrue(data_lines[1].startswith("  "))
        # Charlie is rank 3
        self.assertTrue(data_lines[2].startswith(" 3"))

    def test_tied_rows_blank_score(self):
        rows = [
            LeaderboardRow("Alice", 300),
            LeaderboardRow("Bob", 300),
        ]
        result = make_renderer().render(rows)
        lines = [l for l in result.strip("`").strip().splitlines()]
        data_lines = [l for l in lines[2:] if l.strip()]
        # Second tied row should not repeat the score on the same visual position
        # It starts with "  " (blank rank), and 300 should only appear once in data rows
        self.assertEqual(sum(1 for l in data_lines if "300" in l), 1)


class TestLeaderboardRendererStreak(unittest.TestCase):
    def test_regular_streak_shown_as_number(self):
        rows = [LeaderboardRow("Alice", 100, streak=7)]
        result = make_renderer().render(rows)
        self.assertIn("7", result)

    def test_broken_streak_shows_broken_emoji(self):
        rows = [LeaderboardRow("Alice", 100, broken_streak=3)]
        result = make_renderer().render(rows, broken_streak_emoji="💔")
        self.assertIn("💔", result)

    def test_no_streak_shows_blank(self):
        rows = [LeaderboardRow("Alice", 100)]
        result = make_renderer().render(rows)
        # No streak emoji in data rows; only in header
        lines = result.strip("`").strip().splitlines()
        data_lines = [l for l in lines[2:] if l.strip()]
        # Should not contain 🔥 in data (header line does)
        for line in data_lines:
            self.assertNotIn("🔥", line)

    def test_custom_streak_emoji(self):
        rows = [LeaderboardRow("Alice", 100, streak=3)]
        result = make_renderer().render(rows, streak_emoji="⭐")
        self.assertIn("⭐", result)


class TestLeaderboardRendererNameTruncation(unittest.TestCase):
    def test_long_name_truncated(self):
        long_name = "A" * 30
        rows = [LeaderboardRow(long_name, 100)]
        result = make_renderer().render(rows)
        # Name should be truncated to MAX_NAME_WIDTH
        self.assertNotIn(long_name, result)
        self.assertIn("A" * LeaderboardRenderer.MAX_NAME_WIDTH, result)

    def test_short_name_not_truncated(self):
        rows = [LeaderboardRow("Alice", 100)]
        result = make_renderer().render(rows)
        self.assertIn("Alice", result)


class TestLeaderboardRendererColumnWidths(unittest.TestCase):
    def test_column_width_adapts_to_large_score(self):
        rows = [LeaderboardRow("Alice", 1234567)]
        result = make_renderer().render(rows)
        self.assertIn("1234567", result)

    def test_minimum_score_column_width_is_three(self):
        rows = [LeaderboardRow("Alice", 1)]
        result = make_renderer().render(rows)
        # "pts" header is 3 chars; separator should have at least 3 dashes
        self.assertIn("---", result)

    def test_minimum_streak_column_width_is_two(self):
        rows = [LeaderboardRow("Alice", 100)]
        result = make_renderer().render(rows)
        # Streak header 🔥 should appear surrounded by separator --
        self.assertIn("--", result)

    def test_wide_streak_pads_header(self):
        # streak of 100 → 3 digits → streak col width = 3 → header = " 🔥"
        rows = [LeaderboardRow("Alice", 100, streak=100)]
        result = make_renderer().render(rows)
        self.assertIn("100", result)
        # The fire emoji should be right-aligned (padded with space on left)
        self.assertIn(" 🔥", result)


class TestLeaderboardRendererBadgeColumn(unittest.TestCase):
    def test_badges_appear_on_correct_players(self):
        rows = [
            LeaderboardRow("Alice", 200, badges="🎯🧠"),
            LeaderboardRow("Bob", 100, badges=""),
        ]
        result = make_renderer().render(rows, show_badges=True)
        self.assertIn("🎯", result)
        self.assertIn("🧠", result)

    def test_separator_extended_for_badges(self):
        rows = [LeaderboardRow("Alice", 100, badges="🎯")]
        result = make_renderer().render(rows, show_badges=True)
        # The separator should include the badge divider (---------- at min)
        self.assertIn("----------", result)
