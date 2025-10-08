# tests/bot/managers/test_roles.py
import unittest
from unittest.mock import MagicMock
from src.core.roles import RolesGameMode
from database.database import Database


class TestRolesGameMode(unittest.TestCase):
    def setUp(self):
        # In-memory SQLite database for testing
        self.db = Database(db_path=":memory:")

        # Mock config
        self.mock_config = MagicMock()
        self.mock_config.get.return_value = 10

        self.roles_game_mode = RolesGameMode(self.db, self.mock_config)

        # Populate with some test data
        with self.db.get_conn() as conn:
            # Players
            conn.execute("INSERT INTO players (id, name) VALUES ('1', 'Alice')")
            conn.execute("INSERT INTO players (id, name) VALUES ('2', 'Bob')")
            conn.execute("INSERT INTO players (id, name) VALUES ('3', 'Charlie')")
            conn.execute("INSERT INTO players (id, name) VALUES ('4', 'David')")
            conn.execute("INSERT INTO players (id, name) VALUES ('5', 'Eve')")
            conn.execute("INSERT INTO players (id, name) VALUES ('6', 'Frank')")
            conn.execute("INSERT INTO players (id, name) VALUES ('7', 'Grace')")
            conn.execute("INSERT INTO players (id, name) VALUES ('8', 'Heidi')")
            conn.execute("INSERT INTO players (id, name) VALUES ('9', 'Ivan')")
            conn.execute("INSERT INTO players (id, name) VALUES ('10', 'Judy')")
            conn.execute("INSERT INTO players (id, name) VALUES ('11', 'Mallory')")

            # Guesses
            # Alice: 10 correct
            for i in range(10):
                conn.execute(
                    "INSERT INTO guesses (daily_question_id, player_id, guess_text, is_correct) VALUES (?, ?, ?, ?)",
                    (i, "1", "a", 1),
                )
            # Bob: 5 correct
            for i in range(5):
                conn.execute(
                    "INSERT INTO guesses (daily_question_id, player_id, guess_text, is_correct) VALUES (?, ?, ?, ?)",
                    (i, "2", "a", 1),
                )
            # Charlie: 8 correct
            for i in range(8):
                conn.execute(
                    "INSERT INTO guesses (daily_question_id, player_id, guess_text, is_correct) VALUES (?, ?, ?, ?)",
                    (i, "3", "a", 1),
                )

    def tearDown(self):
        self.db.close()

    def test_get_player_scores(self):
        scores = self.roles_game_mode.get_player_scores()
        self.assertEqual(scores.get("1"), 10)
        self.assertEqual(scores.get("2"), 5)
        self.assertEqual(scores.get("3"), 8)
        self.assertIsNone(scores.get("4"))

    def test_assign_roles(self):
        self.roles_game_mode.assign_roles()
        with self.db.get_conn() as conn:
            # Check for 'First Place' role
            cursor = conn.execute(
                """
                SELECT pr.player_id FROM player_roles pr
                JOIN roles r ON pr.role_id = r.id
                WHERE r.name = 'First Place'
            """
            )
            first_place_player = cursor.fetchone()
            self.assertEqual(first_place_player[0], "1")

            # Check for 'Top 10%' role
            self.mock_config.get.assert_called_with("JBOT_TOP_PLAYER_PERCENTAGE", 10)
            cursor = conn.execute(
                """
                SELECT pr.player_id FROM player_roles pr
                JOIN roles r ON pr.role_id = r.id
                WHERE r.name = 'Top 10%'
            """
            )
            top_10_player = cursor.fetchone()
            # Only Alice should be in the top 10% of the 3 players with scores
            self.assertEqual(top_10_player[0], "1")


if __name__ == "__main__":
    unittest.main()
