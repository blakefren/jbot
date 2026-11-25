import sqlite3
import os
import logging
from contextlib import contextmanager
from datetime import date, datetime
from threading import RLock


# Register adapters/converters for Python 3.12+ compatibility
# This replaces the deprecated default date adapter
def adapt_date_iso(val):
    """Adapt datetime.date to ISO 8601 date."""
    return val.isoformat()


def adapt_datetime_iso(val):
    """Adapt datetime.datetime to ISO 8601 datetime."""
    return val.isoformat()


def convert_date(val):
    """Convert ISO 8601 date to datetime.date object."""
    return date.fromisoformat(val.decode())


def convert_timestamp(val):
    """Convert ISO 8601 datetime to datetime.datetime object."""
    return datetime.fromisoformat(val.decode())


# Register the adapters and converters
sqlite3.register_adapter(date, adapt_date_iso)
sqlite3.register_adapter(datetime, adapt_datetime_iso)
sqlite3.register_converter("date", convert_date)
sqlite3.register_converter("timestamp", convert_timestamp)


class Database:
    """
    Manages the connection to the SQLite database and provides an interface for database operations.
    """

    def __init__(self, db_path="jbot.db"):
        """
        Initializes the Database object, connects to the SQLite database, and creates tables if they don't exist.

        Args:
            db_path (str): The path to the SQLite database file.
        """
        if db_path != ":memory:" and not os.path.isabs(db_path):
            # Resolve relative paths from the project root (parent of db/)
            project_root = os.path.join(os.path.dirname(__file__), "..")
            db_path = os.path.abspath(os.path.join(project_root, db_path))

        if db_path != ":memory:":
            os.makedirs(os.path.dirname(db_path), exist_ok=True)

        self.db_path = db_path
        self.conn = None
        self._transaction_lock = RLock()
        self._transaction_depth = 0
        self._connect()
        self._create_tables()
        self._ensure_event_sequence_columns()

    @contextmanager
    def transaction(self):
        """Group database operations into one commit or rollback boundary.

        Nested calls use SQLite savepoints. The reentrant lock keeps operations
        on this shared connection within the same transaction across threads.
        """
        if self.conn is None:
            raise AttributeError("Database connection is closed")

        with self._transaction_lock:
            depth = self._transaction_depth
            savepoint = f"jbot_transaction_{depth}"
            if depth == 0:
                self.conn.execute("BEGIN IMMEDIATE")
            else:
                self.conn.execute(f"SAVEPOINT {savepoint}")
            self._transaction_depth = depth + 1

            try:
                yield
                if depth == 0:
                    self.conn.commit()
                else:
                    self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            except BaseException:
                try:
                    if depth == 0:
                        self.conn.rollback()
                    else:
                        self.conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                        self.conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                except sqlite3.Error:
                    logging.exception("Failed to roll back database transaction")
                raise
            finally:
                self._transaction_depth = depth

    @contextmanager
    def _connection_scope(self):
        """Serialize use of the shared connection and auto-commit only standalone calls."""
        with self._transaction_lock:
            if self.conn is None:
                raise AttributeError("Database connection is closed")
            if self._transaction_depth:
                yield self.conn
            else:
                with self.conn:
                    yield self.conn

    def _ensure_event_sequence_columns(self):
        for table in ("guesses", "powerup_usage"):
            columns = {
                row[1] for row in self.conn.execute(f"PRAGMA table_info({table})")
            }
            if columns and "event_sequence" not in columns:
                with self.conn:
                    self.conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN event_sequence INTEGER"
                    )

    def _connect(self):
        """
        Establishes a connection to the SQLite database.
        """
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row  # Access columns by name
            if self.db_path != ":memory:":
                self.conn.execute("PRAGMA journal_mode=WAL;")
            logging.info(f"Successfully connected to the database at '{self.db_path}'.")
        except sqlite3.Error as e:
            logging.error(f"Error connecting to the database: {e}")
            raise

    def _create_tables(self):
        """
        Creates the necessary database tables from the schema.sql file.
        """
        try:
            schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
            with open(schema_path, "r") as f:
                schema = f.read()
            self.conn.executescript(schema)
            self.conn.commit()
            logging.info("Database tables created or verified successfully.")
        except sqlite3.Error as e:
            logging.error(f"Error creating tables: {e}")
        except FileNotFoundError:
            logging.error(
                f"Error: 'schema.sql' not found in '{os.path.dirname(__file__)}'."
            )

    def backup(self, dest_path: str):
        """
        Creates a safe, consistent backup of the database to dest_path using
        SQLite's built-in backup API. Safe to call while the DB is in use.

        Args:
            dest_path (str): Full path for the backup file.
        """
        if self.db_path == ":memory:":
            logging.warning("Cannot backup an in-memory database, skipping.")
            return
        dest_conn = sqlite3.connect(dest_path)
        try:
            self.conn.backup(dest_conn)
            logging.info(f"Database backed up to '{dest_path}'.")
        finally:
            dest_conn.close()

    def close(self):
        """
        Closes the database connection.
        """
        if self.conn:
            self.conn.close()
            self.conn = None
            logging.info("Database connection closed.")

    def execute_query(self, query, params=()):
        """
        Executes a given SQL query.

        Args:
            query (str): The SQL query to execute.
            params (tuple, optional): The parameters to substitute into the query. Defaults to ().

        Returns:
            list: A list of rows as dictionaries.
        """
        try:
            with self._connection_scope() as connection:
                cursor = connection.cursor()
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logging.error(f"Error executing query: {e}")
            if self._transaction_depth:
                raise
            return []

    def execute_update(self, query, params=()):
        """
        Executes an update, insert, or delete query.

        Args:
            query (str): The SQL query to execute.
            params (tuple, optional): The parameters to substitute into the query. Defaults to ().

        Returns:
            int: The number of rows affected.
            int: The ID of the newly inserted row.
        """
        try:
            with self._connection_scope() as connection:
                cursor = connection.cursor()
                cursor.execute(query, params)
                return cursor.rowcount, cursor.lastrowid
        except sqlite3.Error as e:
            logging.error(f"Error executing update: {e}")
            if self._transaction_depth:
                raise
            return 0, None

    def execute_script(self, script: str):
        """
        Executes a given SQL script.

        Args:
            script (str): The SQL script to execute.
        """
        try:
            if self._transaction_depth:
                raise RuntimeError("execute_script cannot run inside a transaction")
            with self._connection_scope() as connection:
                connection.executescript(script)
        except sqlite3.Error as e:
            logging.error(f"Error executing script: {e}")
            if self._transaction_depth:
                raise


if __name__ == "__main__":
    # When run as a script, this will initialize the database.
    db_file = os.path.join(os.path.dirname(__file__), "jbot.db")
    db = Database(db_path=db_file)
    logging.info("Database initialized.")
    db.close()
