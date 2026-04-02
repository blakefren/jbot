import unittest
import os
import sys
import sqlite3
import tempfile
import time

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

from db.verify_schema import get_db_tables, parse_schema_file, main


class TestGetDbTables(unittest.TestCase):
    """Tests for get_db_tables."""

    def _make_db(self, ddl_statements: list[str]) -> str:
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = f.name
        f.close()
        conn = sqlite3.connect(db_path)
        for ddl in ddl_statements:
            conn.execute(ddl)
        conn.commit()
        conn.close()
        return db_path

    def _cleanup(self, path):
        time.sleep(0.05)
        try:
            os.unlink(path)
        except (PermissionError, FileNotFoundError):
            pass

    def test_returns_table_and_column_names(self):
        path = self._make_db(
            ["CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, score INTEGER)"]
        )
        try:
            tables = get_db_tables(path)
            self.assertIn("users", tables)
            self.assertEqual(tables["users"], {"id", "name", "score"})
        finally:
            self._cleanup(path)

    def test_multiple_tables(self):
        path = self._make_db(
            [
                "CREATE TABLE users (id INTEGER, name TEXT)",
                "CREATE TABLE posts (id INTEGER, body TEXT)",
            ]
        )
        try:
            tables = get_db_tables(path)
            self.assertIn("users", tables)
            self.assertIn("posts", tables)
            self.assertEqual(tables["posts"], {"id", "body"})
        finally:
            self._cleanup(path)

    def test_empty_database(self):
        path = self._make_db([])
        try:
            self.assertEqual(get_db_tables(path), {})
        finally:
            self._cleanup(path)

    def test_column_names_lowercased(self):
        path = self._make_db(["CREATE TABLE T (MyCol INTEGER, AnotherCol TEXT)"])
        try:
            tables = get_db_tables(path)
            self.assertIn("mycol", tables["t"])
            self.assertIn("anothercol", tables["t"])
        finally:
            self._cleanup(path)


class TestParseSchemaFile(unittest.TestCase):
    """Tests for parse_schema_file."""

    def _write_sql(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_parses_basic_table(self):
        path = self._write_sql(
            "CREATE TABLE IF NOT EXISTS users (id INTEGER, name TEXT);\n"
        )
        try:
            tables = parse_schema_file(path)
            self.assertIn("users", tables)
            self.assertEqual(tables["users"], {"id", "name"})
        finally:
            os.unlink(path)

    def test_strips_constraint_lines(self):
        path = self._write_sql(
            "CREATE TABLE foo (\n"
            "    id INTEGER,\n"
            "    val TEXT,\n"
            "    PRIMARY KEY (id),\n"
            "    FOREIGN KEY (val) REFERENCES bar(x)\n"
            ");\n"
        )
        try:
            tables = parse_schema_file(path)
            self.assertEqual(tables["foo"], {"id", "val"})
        finally:
            os.unlink(path)

    def test_multiple_tables(self):
        path = self._write_sql(
            "CREATE TABLE a (x INTEGER);\n" "CREATE TABLE b (y TEXT, z REAL);\n"
        )
        try:
            tables = parse_schema_file(path)
            self.assertIn("a", tables)
            self.assertIn("b", tables)
            self.assertEqual(tables["b"], {"y", "z"})
        finally:
            os.unlink(path)

    def test_ignores_comments(self):
        path = self._write_sql(
            "-- This is a comment\n"
            "CREATE TABLE users (\n"
            "    id INTEGER, -- inline comment\n"
            "    name TEXT\n"
            ");\n"
        )
        try:
            tables = parse_schema_file(path)
            self.assertEqual(tables["users"], {"id", "name"})
        finally:
            os.unlink(path)

    def test_column_names_lowercased(self):
        path = self._write_sql("CREATE TABLE T (MyCol INTEGER, AnotherCol TEXT);\n")
        try:
            tables = parse_schema_file(path)
            self.assertIn("mycol", tables["t"])
            self.assertIn("anothercol", tables["t"])
        finally:
            os.unlink(path)


class TestMain(unittest.TestCase):
    """Integration tests for main() using temp files."""

    def _make_db(self, ddl_statements: list[str]) -> str:
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = f.name
        f.close()
        conn = sqlite3.connect(db_path)
        for ddl in ddl_statements:
            conn.execute(ddl)
        conn.commit()
        conn.close()
        return db_path

    def _write_sql(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False)
        f.write(content)
        f.close()
        return f.name

    def _cleanup(self, *paths):
        time.sleep(0.05)
        for p in paths:
            try:
                os.unlink(p)
            except (PermissionError, FileNotFoundError):
                pass

    def test_exits_0_when_requirements_met(self):
        db = self._make_db(["CREATE TABLE users (id INTEGER, name TEXT)"])
        sql = self._write_sql("CREATE TABLE users (id INTEGER, name TEXT);\n")
        try:
            with self.assertRaises(SystemExit) as ctx:
                import sys

                sys.argv = ["verify_schema.py", "--db_path", db, "--sql_path", sql]
                main()
            self.assertEqual(ctx.exception.code, 0)
        finally:
            self._cleanup(db, sql)

    def test_exits_1_on_missing_table(self):
        db = self._make_db([])
        sql = self._write_sql("CREATE TABLE users (id INTEGER);\n")
        try:
            with self.assertRaises(SystemExit) as ctx:
                import sys

                sys.argv = ["verify_schema.py", "--db_path", db, "--sql_path", sql]
                main()
            self.assertEqual(ctx.exception.code, 1)
        finally:
            self._cleanup(db, sql)

    def test_exits_1_on_missing_column(self):
        db = self._make_db(["CREATE TABLE users (id INTEGER)"])
        sql = self._write_sql("CREATE TABLE users (id INTEGER, name TEXT);\n")
        try:
            with self.assertRaises(SystemExit) as ctx:
                import sys

                sys.argv = ["verify_schema.py", "--db_path", db, "--sql_path", sql]
                main()
            self.assertEqual(ctx.exception.code, 1)
        finally:
            self._cleanup(db, sql)

    def test_exits_0_with_extra_column_in_db(self):
        """Extra legacy columns in DB are informational only, not errors."""
        db = self._make_db(
            ["CREATE TABLE users (id INTEGER, name TEXT, legacy_col TEXT)"]
        )
        sql = self._write_sql("CREATE TABLE users (id INTEGER, name TEXT);\n")
        try:
            with self.assertRaises(SystemExit) as ctx:
                import sys

                sys.argv = ["verify_schema.py", "--db_path", db, "--sql_path", sql]
                main()
            self.assertEqual(ctx.exception.code, 0)
        finally:
            self._cleanup(db, sql)

    def test_exits_0_with_extra_table_in_db(self):
        """Extra tables in DB (e.g. legacy) are informational only, not errors."""
        db = self._make_db(
            [
                "CREATE TABLE users (id INTEGER)",
                "CREATE TABLE legacy_thing (id INTEGER)",
            ]
        )
        sql = self._write_sql("CREATE TABLE users (id INTEGER);\n")
        try:
            with self.assertRaises(SystemExit) as ctx:
                import sys

                sys.argv = ["verify_schema.py", "--db_path", db, "--sql_path", sql]
                main()
            self.assertEqual(ctx.exception.code, 0)
        finally:
            self._cleanup(db, sql)


if __name__ == "__main__":
    unittest.main()
