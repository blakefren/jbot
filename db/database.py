import sqlite3
import os
import logging
from datetime import date, datetime


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
        # If db_path is not in memory, join with the directory of this file
        if db_path != ":memory:":
            # Go up one level from `core` to `src`. Then join with the provided db_path.
            db_path = os.path.join(os.path.dirname(__file__), "jbot.db")

        self.db_path = db_path
        self.conn = None
        self._connect()
        self._create_tables()

    def _connect(self):
        """
        Establishes a connection to the SQLite database.
        """
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # Access columns by name
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
        if self.conn is None:
            # Mirror test expectation: using the DB after close should raise AttributeError
            raise AttributeError("Database connection is closed")
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logging.error(f"Error executing query: {e}")
            return []

    def get_conn(self):
        """
        Returns the database connection.
        """
        return self.conn

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
        if self.conn is None:
            raise AttributeError("Database connection is closed")
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(query, params)
                return cursor.rowcount, cursor.lastrowid
        except sqlite3.Error as e:
            logging.error(f"Error executing update: {e}")
            return 0, None

    def execute_script(self, script: str):
        """
        Executes a given SQL script.

        Args:
            script (str): The SQL script to execute.
        """
        if self.conn is None:
            raise AttributeError("Database connection is closed")
        try:
            with self.conn:
                self.conn.executescript(script)
        except sqlite3.Error as e:
            logging.error(f"Error executing script: {e}")


if __name__ == "__main__":
    # When run as a script, this will initialize the database.
    db_file = os.path.join(os.path.dirname(__file__), "jbot.db")
    db = Database(db_path=db_file)
    logging.info("Database initialized.")
    db.close()
