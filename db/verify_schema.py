import sqlite3
import argparse
import os
import re


def get_db_schema(db_path):
    """Extracts the schema from the SQLite database."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        )
        # Fetch all results and clean up the SQL
        return [normalize_sql(row[0]) for row in cursor.fetchall()]


def get_sql_file_schema(sql_path):
    """Reads the schema from the .sql file."""
    with open(sql_path, "r") as f:
        content = f.read()
    # Split statements by semicolon and clean them up
    statements = [normalize_sql(s) for s in content.split(";") if s.strip()]
    # Filter out empty strings that can result from splitting
    return [s for s in statements if s]


def normalize_sql(sql_text):
    """Normalizes SQL text to make it comparable."""
    # Remove comments
    sql_text = re.sub(r"--.*", "", sql_text)
    # Replace newlines and tabs with spaces, and collapse multiple spaces
    sql_text = re.sub(r"[\s\n\t]+", " ", sql_text)
    # Remove spaces around commas, parentheses, and equals signs
    sql_text = re.sub(r"\s*([,()=])\s*", r"\1", sql_text)
    # Standardize CREATE TABLE IF NOT EXISTS to CREATE TABLE
    sql_text = sql_text.replace("IF NOT EXISTS ", "")
    return sql_text.strip()


def compare_schemas(db_schema, sql_schema):
    """Compares the two schemas and returns the differences."""
    db_set = set(db_schema)
    sql_set = set(sql_schema)

    missing_in_db = sql_set - db_set
    extra_in_db = db_set - sql_set

    return missing_in_db, extra_in_db


def main():
    parser = argparse.ArgumentParser(
        description="Verify the database schema against a schema.sql file."
    )
    parser.add_argument(
        "--db_path",
        default=os.path.join(os.path.dirname(__file__), "jbot.db"),
        help="Path to the SQLite database file.",
    )
    parser.add_argument(
        "--sql_path",
        default=os.path.join(os.path.dirname(__file__), "schema.sql"),
        help="Path to the schema.sql file.",
    )
    args = parser.parse_args()

    db_schema = get_db_schema(args.db_path)
    sql_schema = get_sql_file_schema(args.sql_path)

    missing, extra = compare_schemas(db_schema, sql_schema)

    if not missing and not extra:
        print("Schema is up to date.")
    else:
        if missing:
            print("Tables/schema definitions missing from the database:")
            for item in missing:
                print(f"  - {item}")
        if extra:
            print("\nTables/schema definitions in the database but not in schema.sql:")
            for item in extra:
                print(f"  - {item}")


if __name__ == "__main__":
    main()
