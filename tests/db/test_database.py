import unittest
import os
import sys
import tempfile
import sqlite3
from unittest.mock import patch, MagicMock

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

    def test_get_conn(self):
        """Test that get_conn returns the database connection."""
        conn = self.db.get_conn()
        self.assertIsNotNone(conn)
        self.assertEqual(conn, self.db.conn)

    def test_execute_script(self):
        """Test execute_script runs a SQL script successfully."""
        script = """
        INSERT INTO players (id, name) VALUES ('script_player1', 'Script Player 1');
        INSERT INTO players (id, name) VALUES ('script_player2', 'Script Player 2');
        """
        self.db.execute_script(script)

        # Verify the data was inserted
        result = self.db.execute_query(
            "SELECT * FROM players WHERE id LIKE 'script_player%'"
        )
        self.assertEqual(len(result), 2)

    def test_execute_script_after_close(self):
        """Test that execute_script raises AttributeError after connection is closed."""
        self.db.close()
        with self.assertRaises(AttributeError):
            self.db.execute_script("SELECT 1;")

    def test_execute_update_after_close(self):
        """Test that execute_update raises AttributeError after connection is closed."""
        self.db.close()
        with self.assertRaises(AttributeError):
            self.db.execute_update("INSERT INTO players (id, name) VALUES ('x', 'y')")

    def test_execute_query_with_sql_error(self):
        """Test that execute_query returns empty list on SQL error."""
        # Invalid SQL syntax
        result = self.db.execute_query("SELECT * FROM nonexistent_table")
        self.assertEqual(result, [])

    def test_execute_update_with_sql_error(self):
        """Test that execute_update returns (0, None) on SQL error."""
        # Try to insert duplicate primary key
        self.db.execute_update(
            "INSERT INTO players (id, name) VALUES ('dup_player', 'Player')"
        )
        affected_rows, lastrowid = self.db.execute_update(
            "INSERT INTO players (id, name) VALUES ('dup_player', 'Duplicate')"
        )
        self.assertEqual(affected_rows, 0)
        self.assertIsNone(lastrowid)

    def test_execute_script_with_sql_error(self):
        """Test that execute_script handles SQL errors gracefully."""
        # Invalid SQL script
        script = "INVALID SQL STATEMENT;"
        # Should not raise, just log the error
        self.db.execute_script(script)

    def test_close_when_already_closed(self):
        """Test that closing an already closed connection is safe."""
        self.db.close()
        # Calling close again should not raise
        self.db.close()
        self.assertIsNone(self.db.conn)


class TestDatabaseFileBasedCreation(unittest.TestCase):
    """Tests for file-based database creation (non-memory path)."""

    def test_file_based_initialization(self):
        """Test that a file-based database uses the correct path in the db directory."""
        # When passing a non-memory path, the Database class uses the db directory
        db = Database(db_path="test.db")
        try:
            # The db_path should be in the db directory, not the passed path
            expected_dir = os.path.dirname(
                os.path.abspath(os.path.join(project_root, "db", "database.py"))
            )
            self.assertTrue(
                db.db_path.startswith(expected_dir) or "jbot.db" in db.db_path
            )
            self.assertIsNotNone(db.conn)
        finally:
            db.close()


class TestDatabaseConnectionError(unittest.TestCase):
    """Tests for database connection error handling."""

    @patch("sqlite3.connect")
    def test_connect_raises_on_sqlite_error(self, mock_connect):
        """Test that connection errors are raised properly."""
        mock_connect.side_effect = sqlite3.Error("Connection failed")
        with self.assertRaises(sqlite3.Error):
            Database(":memory:")


class TestDatabaseSchemaCreationError(unittest.TestCase):
    """Tests for schema creation error handling."""

    def test_create_tables_with_missing_schema_file(self):
        """Test that missing schema.sql file is handled gracefully."""
        with patch(
            "builtins.open", side_effect=FileNotFoundError("schema.sql not found")
        ):
            # Create a mock connection that won't need schema
            with patch.object(Database, "_connect") as mock_connect:
                db = Database.__new__(Database)
                db.db_path = ":memory:"
                db.conn = MagicMock()
                # This should handle FileNotFoundError gracefully
                db._create_tables()

    def test_create_tables_with_sqlite_error(self):
        """Test that SQLite errors during table creation are handled gracefully."""
        with patch.object(Database, "_connect"):
            db = Database.__new__(Database)
            db.db_path = ":memory:"
            db.conn = MagicMock()
            db.conn.executescript.side_effect = sqlite3.Error("Schema error")
            # Mock the file open to return valid schema
            with patch(
                "builtins.open",
                unittest.mock.mock_open(read_data="CREATE TABLE test (id INTEGER);"),
            ):
                # Should not raise, just log the error
                db._create_tables()


if __name__ == "__main__":
    unittest.main()
