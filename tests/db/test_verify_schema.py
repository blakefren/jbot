import unittest
import os
import sys
import sqlite3
import tempfile
from unittest.mock import patch, MagicMock
from io import StringIO

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

from db.verify_schema import (
    get_db_schema,
    get_sql_file_schema,
    normalize_sql,
    compare_schemas,
    main,
)


class TestNormalizeSql(unittest.TestCase):
    """Tests for normalize_sql function."""

    def test_normalize_sql_removes_comments(self):
        """Test that SQL comments are removed."""
        sql = "SELECT * FROM users -- this is a comment"
        result = normalize_sql(sql)
        self.assertNotIn("--", result)
        self.assertNotIn("comment", result)

    def test_normalize_sql_removes_if_not_exists(self):
        """Test that IF NOT EXISTS is removed."""
        sql = "CREATE TABLE IF NOT EXISTS users (id INTEGER)"
        result = normalize_sql(sql)
        self.assertNotIn("IF NOT EXISTS", result)

    def test_normalize_sql_collapses_whitespace(self):
        """Test that multiple whitespaces are collapsed."""
        sql = "SELECT   *    FROM\n\t  users"
        result = normalize_sql(sql)
        self.assertNotIn("  ", result)  # No double spaces
        self.assertNotIn("\n", result)
        self.assertNotIn("\t", result)

    def test_normalize_sql_removes_spaces_around_punctuation(self):
        """Test that spaces around commas, parentheses, equals are removed."""
        sql = "CREATE TABLE users ( id INTEGER , name TEXT )"
        result = normalize_sql(sql)
        self.assertIn("(id", result)
        self.assertIn(",name", result)

    def test_normalize_sql_strips_whitespace(self):
        """Test that leading/trailing whitespace is stripped."""
        sql = "   SELECT * FROM users   "
        result = normalize_sql(sql)
        self.assertFalse(result.startswith(" "))
        self.assertFalse(result.endswith(" "))


class TestGetDbSchema(unittest.TestCase):
    """Tests for get_db_schema function."""

    def test_get_db_schema_returns_normalized_schemas(self):
        """Test that get_db_schema returns normalized table schemas."""
        # Create a temp database file
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
            conn.commit()
            conn.close()

            result = get_db_schema(db_path)

            self.assertEqual(len(result), 1)
            self.assertIn("users", result[0])
        finally:
            os.unlink(db_path)

    def test_get_db_schema_empty_database(self):
        """Test get_db_schema with empty database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.close()

            result = get_db_schema(db_path)
            self.assertEqual(result, [])
        finally:
            os.unlink(db_path)


class TestGetSqlFileSchema(unittest.TestCase):
    """Tests for get_sql_file_schema function."""

    def test_get_sql_file_schema_reads_and_normalizes(self):
        """Test that get_sql_file_schema reads and normalizes SQL file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write("CREATE TABLE IF NOT EXISTS users (id INTEGER);\n")
            f.write("CREATE TABLE IF NOT EXISTS posts (id INTEGER);")
            sql_path = f.name

        try:
            result = get_sql_file_schema(sql_path)

            self.assertEqual(len(result), 2)
            # IF NOT EXISTS should be removed
            for schema in result:
                self.assertNotIn("IF NOT EXISTS", schema)
        finally:
            os.unlink(sql_path)

    def test_get_sql_file_schema_filters_empty_statements(self):
        """Test that empty statements are filtered out."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write("CREATE TABLE users (id INTEGER);\n;\n;")
            sql_path = f.name

        try:
            result = get_sql_file_schema(sql_path)
            # Only one valid statement
            self.assertEqual(len(result), 1)
        finally:
            os.unlink(sql_path)


class TestCompareSchemas(unittest.TestCase):
    """Tests for compare_schemas function."""

    def test_compare_schemas_no_differences(self):
        """Test compare_schemas when schemas match exactly."""
        db_schema = ["CREATE TABLE users(id INTEGER)"]
        sql_schema = ["CREATE TABLE users(id INTEGER)"]

        missing, extra = compare_schemas(db_schema, sql_schema)

        self.assertEqual(missing, set())
        self.assertEqual(extra, set())

    def test_compare_schemas_missing_in_db(self):
        """Test compare_schemas when tables are missing from database."""
        db_schema = ["CREATE TABLE users(id INTEGER)"]
        sql_schema = [
            "CREATE TABLE users(id INTEGER)",
            "CREATE TABLE posts(id INTEGER)",
        ]

        missing, extra = compare_schemas(db_schema, sql_schema)

        self.assertIn("CREATE TABLE posts(id INTEGER)", missing)
        self.assertEqual(extra, set())

    def test_compare_schemas_extra_in_db(self):
        """Test compare_schemas when database has extra tables."""
        db_schema = [
            "CREATE TABLE users(id INTEGER)",
            "CREATE TABLE old_table(id INTEGER)",
        ]
        sql_schema = ["CREATE TABLE users(id INTEGER)"]

        missing, extra = compare_schemas(db_schema, sql_schema)

        self.assertEqual(missing, set())
        self.assertIn("CREATE TABLE old_table(id INTEGER)", extra)

    def test_compare_schemas_both_missing_and_extra(self):
        """Test compare_schemas with both missing and extra tables."""
        db_schema = [
            "CREATE TABLE users(id INTEGER)",
            "CREATE TABLE old_table(id INTEGER)",
        ]
        sql_schema = [
            "CREATE TABLE users(id INTEGER)",
            "CREATE TABLE new_table(id INTEGER)",
        ]

        missing, extra = compare_schemas(db_schema, sql_schema)

        self.assertIn("CREATE TABLE new_table(id INTEGER)", missing)
        self.assertIn("CREATE TABLE old_table(id INTEGER)", extra)


class TestMain(unittest.TestCase):
    """Tests for the main function."""

    @patch("db.verify_schema.get_db_schema")
    @patch("db.verify_schema.get_sql_file_schema")
    @patch("builtins.print")
    def test_main_schema_up_to_date(self, mock_print, mock_get_sql, mock_get_db):
        """Test main when schema is up to date."""
        mock_get_db.return_value = ["CREATE TABLE users(id INTEGER)"]
        mock_get_sql.return_value = ["CREATE TABLE users(id INTEGER)"]

        with patch(
            "sys.argv",
            ["verify_schema.py", "--db_path", "test.db", "--sql_path", "test.sql"],
        ):
            main()

        mock_print.assert_called_with("Schema is up to date.")

    @patch("db.verify_schema.get_db_schema")
    @patch("db.verify_schema.get_sql_file_schema")
    @patch("builtins.print")
    def test_main_missing_tables(self, mock_print, mock_get_sql, mock_get_db):
        """Test main when tables are missing from database."""
        mock_get_db.return_value = []
        mock_get_sql.return_value = ["CREATE TABLE users(id INTEGER)"]

        with patch(
            "sys.argv",
            ["verify_schema.py", "--db_path", "test.db", "--sql_path", "test.sql"],
        ):
            main()

        mock_print.assert_any_call(
            "Tables/schema definitions missing from the database:"
        )

    @patch("db.verify_schema.get_db_schema")
    @patch("db.verify_schema.get_sql_file_schema")
    @patch("builtins.print")
    def test_main_extra_tables(self, mock_print, mock_get_sql, mock_get_db):
        """Test main when database has extra tables."""
        mock_get_db.return_value = [
            "CREATE TABLE users(id INTEGER)",
            "CREATE TABLE extra(id INTEGER)",
        ]
        mock_get_sql.return_value = ["CREATE TABLE users(id INTEGER)"]

        with patch(
            "sys.argv",
            ["verify_schema.py", "--db_path", "test.db", "--sql_path", "test.sql"],
        ):
            main()

        mock_print.assert_any_call(
            "\nTables/schema definitions in the database but not in schema.sql:"
        )

    @patch("db.verify_schema.get_db_schema")
    @patch("db.verify_schema.get_sql_file_schema")
    @patch("builtins.print")
    def test_main_uses_default_paths(self, mock_print, mock_get_sql, mock_get_db):
        """Test main uses default paths when not specified."""
        mock_get_db.return_value = ["CREATE TABLE users(id INTEGER)"]
        mock_get_sql.return_value = ["CREATE TABLE users(id INTEGER)"]

        with patch("sys.argv", ["verify_schema.py"]):
            main()

        # Should use default paths (relative to db/ directory)
        # The actual paths will be absolute, so just check they were called
        self.assertTrue(mock_get_db.called)
        self.assertTrue(mock_get_sql.called)


if __name__ == "__main__":
    unittest.main()
