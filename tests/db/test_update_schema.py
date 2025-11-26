import unittest
import os
import sys
import sqlite3
import tempfile
from unittest.mock import patch, MagicMock

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

from db.update_schema import (
    get_db_connection,
    get_current_schema,
    get_target_schema,
    parse_schema,
    compare_schemas,
    update_schema,
    main,
)


class TestGetDbConnection(unittest.TestCase):
    """Tests for get_db_connection function."""

    @patch("sqlite3.connect")
    def test_get_db_connection_returns_connection(self, mock_connect):
        """Test that get_db_connection returns a sqlite3 connection."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        result = get_db_connection()

        self.assertEqual(result, mock_conn)
        mock_connect.assert_called_once()


class TestGetCurrentSchema(unittest.TestCase):
    """Tests for get_current_schema function."""

    def test_get_current_schema_returns_table_schemas(self):
        """Test that get_current_schema returns list of table creation SQL."""
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE another_table (id INTEGER)")
        conn.commit()

        result = get_current_schema(conn)

        self.assertEqual(len(result), 2)
        self.assertTrue(any("test_table" in schema for schema in result))
        self.assertTrue(any("another_table" in schema for schema in result))
        conn.close()

    def test_get_current_schema_empty_database(self):
        """Test that get_current_schema returns empty list for empty database."""
        conn = sqlite3.connect(":memory:")

        result = get_current_schema(conn)

        self.assertEqual(result, [])
        conn.close()


class TestGetTargetSchema(unittest.TestCase):
    """Tests for get_target_schema function."""

    def test_get_target_schema_reads_file(self):
        """Test that get_target_schema reads the schema.sql file."""
        # This test uses the actual schema.sql file
        result = get_target_schema()

        self.assertIsInstance(result, str)
        self.assertIn("CREATE TABLE", result)
        self.assertIn("questions", result)


class TestParseSchema(unittest.TestCase):
    """Tests for parse_schema function."""

    def test_parse_schema_with_if_not_exists(self):
        """Test parsing schema with IF NOT EXISTS clause."""
        schema_sql = """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT
        );
        """
        result = parse_schema(schema_sql)

        self.assertIn("users", result)
        self.assertIn("CREATE TABLE", result["users"])
        self.assertNotIn("IF NOT EXISTS", result["users"])

    def test_parse_schema_without_if_not_exists(self):
        """Test parsing schema without IF NOT EXISTS clause."""
        schema_sql = """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT
        );
        """
        result = parse_schema(schema_sql)

        self.assertIn("users", result)
        self.assertIn("CREATE TABLE", result["users"])

    def test_parse_schema_multiple_tables(self):
        """Test parsing schema with multiple tables."""
        schema_sql = """
        CREATE TABLE IF NOT EXISTS users (id INTEGER);
        CREATE TABLE IF NOT EXISTS posts (id INTEGER);
        CREATE TABLE IF NOT EXISTS comments (id INTEGER);
        """
        result = parse_schema(schema_sql)

        self.assertEqual(len(result), 3)
        self.assertIn("users", result)
        self.assertIn("posts", result)
        self.assertIn("comments", result)

    def test_parse_schema_with_comments(self):
        """Test parsing schema with SQL comments."""
        schema_sql = """
        -- This is a comment
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, -- inline comment
            name TEXT
        );
        """
        result = parse_schema(schema_sql)

        self.assertIn("users", result)

    def test_parse_schema_empty_string(self):
        """Test parsing empty schema string."""
        result = parse_schema("")
        self.assertEqual(result, {})

    def test_parse_schema_no_create_table(self):
        """Test parsing schema with no CREATE TABLE statements."""
        schema_sql = "SELECT * FROM users;"
        result = parse_schema(schema_sql)
        self.assertEqual(result, {})

    def test_parse_schema_malformed_statement(self):
        """Test parsing schema with malformed statement that can't be parsed."""
        # A statement that has CREATE TABLE but malformed format
        schema_sql = "CREATE TABLE;"  # Missing table name and columns
        result = parse_schema(schema_sql)
        # Should handle gracefully, likely empty dict
        self.assertIsInstance(result, dict)


class TestCompareSchemas(unittest.TestCase):
    """Tests for compare_schemas function."""

    def test_compare_schemas_finds_new_tables(self):
        """Test that compare_schemas identifies new tables."""
        current_schema_list = ["CREATE TABLE users (id INTEGER)"]
        target_schema_sql = """
        CREATE TABLE IF NOT EXISTS users (id INTEGER);
        CREATE TABLE IF NOT EXISTS posts (id INTEGER);
        """

        new_tables, modified_tables = compare_schemas(
            current_schema_list, target_schema_sql
        )

        self.assertIn("posts", new_tables)
        self.assertNotIn("users", new_tables)

    def test_compare_schemas_finds_modified_tables(self):
        """Test that compare_schemas identifies modified tables."""
        current_schema_list = ["CREATE TABLE users (id INTEGER)"]
        target_schema_sql = """
        CREATE TABLE IF NOT EXISTS users (id INTEGER, name TEXT);
        """

        new_tables, modified_tables = compare_schemas(
            current_schema_list, target_schema_sql
        )

        self.assertIn("users", modified_tables)
        self.assertIn("current", modified_tables["users"])
        self.assertIn("target", modified_tables["users"])

    def test_compare_schemas_no_differences(self):
        """Test compare_schemas when schemas match."""
        current_schema_list = ["CREATE TABLE users (id INTEGER)"]
        target_schema_sql = "CREATE TABLE IF NOT EXISTS users (id INTEGER);"

        new_tables, modified_tables = compare_schemas(
            current_schema_list, target_schema_sql
        )

        self.assertEqual(new_tables, {})
        self.assertEqual(modified_tables, {})


class TestUpdateSchema(unittest.TestCase):
    """Tests for update_schema function."""

    def test_update_schema_creates_new_table(self):
        """Test that update_schema creates new tables."""
        conn = sqlite3.connect(":memory:")
        new_schema = "CREATE TABLE new_table (id INTEGER PRIMARY KEY);"

        with patch("builtins.print") as mock_print:
            update_schema(conn, new_schema)

        # Verify the table was created
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='new_table'"
        )
        result = cursor.fetchone()
        self.assertIsNotNone(result)
        conn.close()

    def test_update_schema_handles_error(self):
        """Test that update_schema handles SQL errors."""
        conn = sqlite3.connect(":memory:")
        invalid_schema = "INVALID SQL STATEMENT;"

        with patch("builtins.print") as mock_print:
            update_schema(conn, invalid_schema)
            # Should print error message
            mock_print.assert_called()

        conn.close()


class TestMain(unittest.TestCase):
    """Tests for the main function."""

    @patch("db.update_schema.get_db_connection")
    @patch("db.update_schema.get_current_schema")
    @patch("db.update_schema.get_target_schema")
    @patch("builtins.print")
    def test_main_schema_up_to_date(
        self, mock_print, mock_get_target, mock_get_current, mock_get_conn
    ):
        """Test main when schema is already up to date."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_get_current.return_value = ["CREATE TABLE users(id INTEGER)"]
        mock_get_target.return_value = "CREATE TABLE IF NOT EXISTS users(id INTEGER);"

        main()

        mock_print.assert_any_call("Database schema is up to date.")
        mock_conn.close.assert_called_once()

    @patch("db.update_schema.get_db_connection")
    @patch("db.update_schema.get_current_schema")
    @patch("db.update_schema.get_target_schema")
    @patch("builtins.input", return_value="n")
    @patch("builtins.print")
    def test_main_new_tables_cancelled(
        self, mock_print, mock_input, mock_get_target, mock_get_current, mock_get_conn
    ):
        """Test main when new tables exist but user cancels."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_get_current.return_value = []
        mock_get_target.return_value = "CREATE TABLE IF NOT EXISTS users(id INTEGER);"

        main()

        mock_print.assert_any_call("Schema update cancelled.")
        mock_conn.close.assert_called_once()

    @patch("db.update_schema.get_db_connection")
    @patch("db.update_schema.get_current_schema")
    @patch("db.update_schema.get_target_schema")
    @patch("builtins.input", return_value="y")
    @patch("builtins.print")
    def test_main_new_tables_applied(
        self, mock_print, mock_input, mock_get_target, mock_get_current, mock_get_conn
    ):
        """Test main when new tables exist and user confirms."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn
        mock_get_current.return_value = []
        mock_get_target.return_value = "CREATE TABLE IF NOT EXISTS users(id INTEGER);"

        main()

        mock_cursor.execute.assert_called()
        mock_conn.commit.assert_called_once()
        mock_print.assert_any_call("Schema updated.")
        mock_conn.close.assert_called_once()

    @patch("db.update_schema.get_db_connection")
    @patch("db.update_schema.get_current_schema")
    @patch("db.update_schema.get_target_schema")
    @patch("builtins.input", return_value="y")
    @patch("builtins.print")
    def test_main_handles_operational_error(
        self, mock_print, mock_input, mock_get_target, mock_get_current, mock_get_conn
    ):
        """Test main handles OperationalError when executing SQL."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = sqlite3.OperationalError("test error")
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn
        mock_get_current.return_value = []
        mock_get_target.return_value = "CREATE TABLE IF NOT EXISTS users(id INTEGER);"

        main()

        # Should handle the error and still close the connection
        mock_conn.close.assert_called_once()

    @patch("db.update_schema.get_db_connection")
    @patch("db.update_schema.get_current_schema")
    @patch("db.update_schema.get_target_schema")
    @patch("builtins.input", return_value="n")
    @patch("builtins.print")
    def test_main_handles_malformed_target_schema(
        self, mock_print, mock_input, mock_get_target, mock_get_current, mock_get_conn
    ):
        """Test main handles target schema with edge case CREATE TABLE syntax.

        Note: The IndexError exception handler at lines 141-142 in update_schema.py
        appears to be unreachable code due to how Python's str.split() works.
        When "CREATE TABLE" is in the statement, split("CREATE TABLE")[1] always
        returns at least an empty string, never raising IndexError.
        This test verifies the function handles minimal CREATE TABLE statements.
        """
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_get_current.return_value = []
        # Minimal CREATE TABLE statement - parses but creates empty table name
        mock_get_target.return_value = "CREATE TABLE"

        main()

        # Function should complete and close connection
        mock_conn.close.assert_called_once()

    @patch("db.update_schema.get_db_connection")
    @patch("db.update_schema.get_current_schema")
    @patch("db.update_schema.get_target_schema")
    @patch("builtins.input", return_value="n")
    @patch("builtins.print")
    def test_main_parses_table_without_if_not_exists(
        self, mock_print, mock_input, mock_get_target, mock_get_current, mock_get_conn
    ):
        """Test main parses CREATE TABLE statements without IF NOT EXISTS (line 137)."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_get_current.return_value = []
        # CREATE TABLE without IF NOT EXISTS clause - triggers else branch at line 137
        mock_get_target.return_value = "CREATE TABLE new_users (id INTEGER);"

        main()

        # Should detect this as a new table and prompt for confirmation
        mock_print.assert_any_call("The following new tables are proposed:")
        mock_conn.close.assert_called_once()

    @patch("db.update_schema.get_db_connection")
    @patch("db.update_schema.get_current_schema")
    @patch("db.update_schema.get_target_schema")
    @patch("builtins.input", return_value="n")
    @patch("builtins.print")
    def test_main_handles_current_schema_parsing_error(
        self, mock_print, mock_input, mock_get_target, mock_get_current, mock_get_conn
    ):
        """Test main handles IndexError when parsing current schema (lines 119-120)."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        # Current schema without "CREATE TABLE" text causes IndexError on split()[1]
        # This triggers the except IndexError: continue at lines 119-120
        mock_get_current.return_value = ["SOME TEXT WITHOUT THE EXPECTED FORMAT"]
        mock_get_target.return_value = "CREATE TABLE IF NOT EXISTS users(id INTEGER);"

        # Should handle gracefully and close connection
        main()

        mock_conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
