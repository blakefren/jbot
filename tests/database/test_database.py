import unittest
import os
import sys
# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)
from db.database import Database


class TestDatabase(unittest.TestCase):

    def setUp(self):
        """Set up a temporary database for testing."""
        self.db_path = ":memory:"
        # To test file-based creation, uncomment the following line
        # self.db_path = "test.db"
        self.db = Database(self.db_path)

    def tearDown(self):
        """Close the connection and remove the temporary database file."""
        self.db.close()
        if self.db_path != ":memory:":
            os.remove(self.db_path)

    def test_initialization(self):
        """Test that the database and tables are created on initialization."""
        self.assertIsNotNone(self.db.conn)
        # Check if tables were created
        query = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        tables = self.db.execute_query(query)
        table_names = [table["name"] for table in tables]
        self.assertIn("questions", table_names)
        self.assertIn("daily_questions", table_names)
        self.assertIn("players", table_names)
        self.assertIn("guesses", table_names)
        self.assertIn("messages", table_names)

    def test_execute_update_insert(self):
        """Test inserting data with execute_update."""
        query = "INSERT INTO players (id, name) VALUES (?, ?)"
        params = ("test_player_id", "Test Player")
        affected_rows, _ = self.db.execute_update(query, params)
        self.assertEqual(affected_rows, 1)

        # Verify the data was inserted
        result = self.db.execute_query(
            "SELECT * FROM players WHERE id = 'test_player_id'"
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Test Player")

    def test_execute_query(self):
        """Test querying data with execute_query."""
        self.db.execute_update(
            "INSERT INTO players (id, name) VALUES ('query_player', 'Query Player')"
        )

        query = "SELECT * FROM players WHERE id = ?"
        params = ("query_player",)
        result = self.db.execute_query(query, params)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "query_player")
        self.assertEqual(result[0]["name"], "Query Player")

    def test_execute_update_update(self):
        """Test updating data with execute_update."""
        self.db.execute_update(
            "INSERT INTO players (id, name) VALUES ('update_player', 'Initial Name')"
        )

        query = "UPDATE players SET name = ? WHERE id = ?"
        params = ("Updated Name", "update_player")
        affected_rows, _ = self.db.execute_update(query, params)
        self.assertEqual(affected_rows, 1)

        # Verify the data was updated
        result = self.db.execute_query(
            "SELECT * FROM players WHERE id = 'update_player'"
        )
        self.assertEqual(result[0]["name"], "Updated Name")

    def test_execute_update_delete(self):
        """Test deleting data with execute_update."""
        self.db.execute_update(
            "INSERT INTO players (id, name) VALUES ('delete_player', 'Delete Me')"
        )

        query = "DELETE FROM players WHERE id = ?"
        params = ("delete_player",)
        affected_rows, _ = self.db.execute_update(query, params)
        self.assertEqual(affected_rows, 1)

        # Verify the data was deleted
        result = self.db.execute_query(
            "SELECT * FROM players WHERE id = 'delete_player'"
        )
        self.assertEqual(len(result), 0)

    def test_close_connection(self):
        """Test that the database connection can be closed."""
        self.db.close()
        self.assertIsNone(self.db.conn)
        # After closing, trying to use the connection should raise an error
        with self.assertRaises(AttributeError):
            self.db.execute_query("SELECT 1")


if __name__ == "__main__":
    unittest.main()
