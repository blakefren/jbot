import sqlite3
import argparse
import os
import re
import sys


def get_db_tables(db_path: str) -> dict[str, set[str]]:
    """
    Returns a dict of {table_name: {column_name, ...}} for every table in the DB,
    using PRAGMA table_info which gives reliable per-column metadata regardless of
    how the table was migrated (ADD COLUMN always appends; DDL strings diverge).
    """
    tables = {}
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        )
        table_names = [row["name"] for row in cursor.fetchall()]
        for name in table_names:
            cursor.execute(f"PRAGMA table_info({name})")
            tables[name.lower()] = {row["name"].lower() for row in cursor.fetchall()}
    return tables


def parse_schema_file(sql_path: str) -> dict[str, set[str]]:
    """
    Parses CREATE TABLE statements from a .sql file.
    Returns {table_name: {column_name, ...}}.
    Constraint lines (PRIMARY KEY, FOREIGN KEY, UNIQUE, CHECK) are excluded.
    """
    with open(sql_path, "r") as f:
        content = f.read()

    # Strip line comments
    content = re.sub(r"--[^\n]*", "", content)

    tables = {}
    # Match CREATE TABLE [IF NOT EXISTS] name ( ... )
    for match in re.finditer(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"']?(\w+)[\"']?\s*\((.+?)\)",
        content,
        re.IGNORECASE | re.DOTALL,
    ):
        table_name = match.group(1).lower()
        body = match.group(2)

        columns = set()
        for line in body.split(","):
            line = line.strip()
            if not line:
                continue
            upper = line.upper()
            # Skip table-level constraints
            if any(
                upper.startswith(kw)
                for kw in ("PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "CHECK")
            ):
                continue
            # First token is the column name (strip any quoting)
            col_name = re.split(r"\s+", line)[0].strip("\"'`").lower()
            if col_name:
                columns.add(col_name)

        tables[table_name] = columns

    return tables


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

    db_tables = get_db_tables(args.db_path)
    schema_tables = parse_schema_file(args.sql_path)

    errors: list[str] = []
    info: list[str] = []

    # --- Check everything schema.sql requires is present in the DB ---
    for table, schema_cols in schema_tables.items():
        if table not in db_tables:
            errors.append(f"  [MISSING TABLE]  {table}")
            continue
        db_cols = db_tables[table]
        for col in sorted(schema_cols):
            if col not in db_cols:
                errors.append(f"  [MISSING COLUMN] {table}.{col}")

    # --- Report extra things in DB (informational only) ---
    extra_tables = set(db_tables) - set(schema_tables)
    for table in sorted(extra_tables):
        info.append(
            f"  [EXTRA TABLE]    {table}  (not in schema.sql — possibly legacy)"
        )

    for table, schema_cols in schema_tables.items():
        if table not in db_tables:
            continue
        extra_cols = db_tables[table] - schema_cols
        for col in sorted(extra_cols):
            info.append(
                f"  [EXTRA COLUMN]   {table}.{col}  (not in schema.sql — possibly legacy)"
            )

    # --- Output ---
    if errors:
        print("ERRORS — schema.sql requirements not met in database:")
        for e in errors:
            print(e)
    if info:
        print("\nINFO — extra items in database not defined in schema.sql:")
        for i in info:
            print(i)

    if not errors and not info:
        print("Schema is up to date.")
    elif not errors:
        print("\nSchema requirements satisfied (extra items are informational only).")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
