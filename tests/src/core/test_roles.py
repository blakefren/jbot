# tests/bot/managers/test_roles.py
import unittest
from unittest.mock import MagicMock
from src.core.roles import RolesGameMode
from src.core.data_manager import DataManager
from db.database import Database


class TestRolesGameMode(unittest.TestCase):
    def setUp(self):
        # In-memory SQLite database for testing
        self.db = Database(db_path=":memory:")
        self.data_manager = DataManager(self.db)

        # Mock config
        self.mock_config = MagicMock()
        self.mock_config.get.return_value = 10

        self.roles_game_mode = RolesGameMode(self.data_manager, self.mock_config)

        # Populate with some test data
        with self.db.get_conn() as conn:
            # Players
            conn.execute(
                "INSERT INTO players (id, name, score) VALUES ('1', 'Alice', 10)"
            )
            conn.execute("INSERT INTO players (id, name, score) VALUES ('2', 'Bob', 5)")
            conn.execute(
                "INSERT INTO players (id, name, score) VALUES ('3', 'Charlie', 8)"
            )
            conn.execute(
                "INSERT INTO players (id, name, score) VALUES ('4', 'David', 0)"
            )
            conn.execute("INSERT INTO players (id, name, score) VALUES ('5', 'Eve', 0)")
            conn.execute(
                "INSERT INTO players (id, name, score) VALUES ('6', 'Frank', 0)"
            )
            conn.execute(
                "INSERT INTO players (id, name, score) VALUES ('7', 'Grace', 0)"
            )
            conn.execute(
                "INSERT INTO players (id, name, score) VALUES ('8', 'Heidi', 0)"
            )
            conn.execute(
                "INSERT INTO players (id, name, score) VALUES ('9', 'Ivan', 0)"
            )
            conn.execute(
                "INSERT INTO players (id, name, score) VALUES ('10', 'Judy', 0)"
            )
            conn.execute(
                "INSERT INTO players (id, name, score) VALUES ('11', 'Mallory', 0)"
            )

    def tearDown(self):
        self.db.close()

    def test_get_player_scores(self):
        scores = self.roles_game_mode.get_player_scores()
        self.assertEqual(len(scores), 3)
        self.assertEqual(scores[0]["id"], "1")
        self.assertEqual(scores[0]["score"], 10)
        self.assertEqual(scores[1]["id"], "3")
        self.assertEqual(scores[1]["score"], 8)
        self.assertEqual(scores[2]["id"], "2")
        self.assertEqual(scores[2]["score"], 5)

    def test_assign_roles(self):
        self.roles_game_mode.assign_roles()
        with self.db.get_conn() as conn:
            # Check for 'First Place' role
            cursor = conn.execute(
                """
                SELECT pr.player_id FROM player_roles pr
                JOIN roles r ON pr.role_id = r.id
                WHERE r.name = 'first place'
            """
            )
            first_place_players = [row[0] for row in cursor.fetchall()]
            self.assertEqual(first_place_players, ["1"])

    def test_assign_roles_tie_for_first(self):
        # Make Bob have the same score as Alice
        with self.db.get_conn() as conn:
            conn.execute("UPDATE players SET score = 10 WHERE id = '2'")

        self.roles_game_mode.assign_roles()
        with self.db.get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT pr.player_id FROM player_roles pr
                JOIN roles r ON pr.role_id = r.id
                WHERE r.name = 'first place'
            """
            )
            first_place_players = sorted([row[0] for row in cursor.fetchall()])
            self.assertEqual(first_place_players, ["1", "2"])

    def test_assign_roles_clears_old_roles(self):
        # Pre-assign a role to a player who shouldn't have it
        self.roles_game_mode.assign_role_to_player("2", "first place")

        # Run the assignment
        self.roles_game_mode.assign_roles()

        with self.db.get_conn() as conn:
            # Check that Bob no longer has 'first place'
            cursor = conn.execute(
                """
                SELECT pr.player_id FROM player_roles pr
                JOIN roles r ON pr.role_id = r.id
                WHERE r.name = 'first place'
            """
            )
            first_place_players = [row[0] for row in cursor.fetchall()]
            self.assertNotIn("2", first_place_players)
            self.assertIn("1", first_place_players)


if __name__ == "__main__":
    unittest.main()
