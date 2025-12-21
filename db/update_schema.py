import sqlite3
import os


def get_db_connection():
    """Establishes a connection to the database."""
    db_path = os.path.join(os.path.dirname(__file__), "jbot.db")
    return sqlite3.connect(db_path)


def get_current_schema(conn):
    """Retrieves the current schema from the database."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    )
    return [row[0] for row in cursor.fetchall()]


def get_target_schema():
    """Reads the target schema from the schema.sql file."""
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r") as f:
        return f.read()


def parse_schema(schema_sql):
    """Parses CREATE TABLE statements and returns a dictionary of table_name: statement."""
    statements = [s.strip() for s in schema_sql.strip().split(";") if s.strip()]
    schema_dict = {}
    for statement in statements:
        if "CREATE TABLE" in statement:
            # This parsing is simplistic and might need to be more robust
            try:
                if "IF NOT EXISTS" in statement:
                    table_name = (
                        statement.split("IF NOT EXISTS ")[1].split(" (")[0].strip()
                    )
                else:
                    table_name = (
                        statement.split("CREATE TABLE ")[1].split(" (")[0].strip()
                    )

                # Normalize by removing comments and standardizing whitespace
                lines = []
                for line in statement.splitlines():
                    line = line.strip()
                    if line.startswith("--"):
                        continue
                    # Remove inline comments
                    if "--" in line:
                        line = line.split("--")[0].strip()
                    lines.append(line)

                normalized_statement = " ".join(lines)
                normalized_statement = " ".join(normalized_statement.split()).replace(
                    "IF NOT EXISTS ", ""
                )
                schema_dict[table_name] = normalized_statement
            except IndexError:
                print(f"Warning: Could not parse table name from: {statement}")
    return schema_dict


def compare_schemas(current_schema_list, target_schema_sql):
    """
    Compares the current and target schemas and returns the differences.
    """
    current_schema_sql = ";\n".join(current_schema_list)
    current_schema_dict = parse_schema(current_schema_sql)
    target_schema_dict = parse_schema(target_schema_sql)

    new_tables = {}
    modified_tables = {}

    for table_name, target_statement in target_schema_dict.items():
        if table_name not in current_schema_dict:
            new_tables[table_name] = target_statement
        else:
            current_statement = current_schema_dict[table_name]
            # Simple string comparison after normalization
            if current_statement != target_statement:
                modified_tables[table_name] = {
                    "current": current_statement,
                    "target": target_statement,
                }

    return new_tables, modified_tables


def get_db_columns(conn, table_name):
    """Retrieves the set of column names for a table from the database."""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def parse_columns(create_statement):
    """
    Extracts column definitions from a CREATE TABLE statement.
    Returns a dict of {column_name: full_definition_string}.
    """
    # Extract content inside the first ( and last )
    start = create_statement.find("(")
    end = create_statement.rfind(")")
    if start == -1 or end == -1:
        return {}

    content = create_statement[start + 1 : end]

    # Split by comma, respecting parentheses
    definitions = []
    current = []
    paren_depth = 0
    for char in content:
        if char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1
        elif char == "," and paren_depth == 0:
            definitions.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if current:
        definitions.append("".join(current).strip())

    columns = {}
    for definition in definitions:
        # Skip table constraints
        upper_def = definition.upper()
        if (
            upper_def.startswith("PRIMARY KEY")
            or upper_def.startswith("FOREIGN KEY")
            or upper_def.startswith("CONSTRAINT")
            or upper_def.startswith("UNIQUE")
            or upper_def.startswith("CHECK")
        ):
            continue

        # Extract column name (first token)
        parts = definition.split()
        if parts:
            col_name = parts[0].strip('"[]`')
            columns[col_name] = definition

    return columns


def update_schema(conn, new_schema):
    """Applies the new schema to the database."""
    cursor = conn.cursor()
    try:
        cursor.executescript(new_schema)
        conn.commit()
        print("Database schema updated successfully.")
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        conn.rollback()


import difflib


def main():
    """Main function to run the schema update process."""
    conn = get_db_connection()

    current_schema_list = get_current_schema(conn)
    target_schema_sql = get_target_schema()

    # Get current table names from the database
    current_tables = set()
    for schema in current_schema_list:
        try:
            # This parsing is simplistic and might need to be more robust
            table_name = schema.split("CREATE TABLE")[1].lstrip().split("(")[0].strip()
            current_tables.add(table_name)
        except IndexError:
            continue

    # Get target table names and their CREATE statements
    target_statements = [
        s.strip() for s in target_schema_sql.strip().split(";") if s.strip()
    ]

    new_tables_sql = []
    for statement in target_statements:
        if "CREATE TABLE" in statement:
            try:
                table_name_part = statement.split("CREATE TABLE")[1]
                if "IF NOT EXISTS" in table_name_part:
                    table_name = (
                        table_name_part.split("IF NOT EXISTS")[1].split("(")[0].strip()
                    )
                else:
                    table_name = table_name_part.split("(")[0].strip()

                if table_name not in current_tables:
                    new_tables_sql.append(statement + ";")
            except IndexError:  # pragma: no cover
                # This branch is unreachable due to how str.split() works
                print(f"Warning: Could not parse statement: {statement}")

    alter_statements = []
    target_schema_dict = parse_schema(target_schema_sql)

    for table_name, create_statement in target_schema_dict.items():
        if table_name in current_tables:
            db_columns = get_db_columns(conn, table_name)
            target_columns = parse_columns(create_statement)

            for col_name, col_def in target_columns.items():
                if col_name not in db_columns:
                    print(
                        f"Detected missing column '{col_name}' in table '{table_name}'"
                    )
                    alter_statements.append(
                        f"ALTER TABLE {table_name} ADD COLUMN {col_def};"
                    )

    if not new_tables_sql and not alter_statements:
        print("Database schema is up to date.")
        conn.close()
        return

    if new_tables_sql:
        print("The following new tables are proposed:")
        for sql in new_tables_sql:
            print(sql)

    if alter_statements:
        print("The following schema updates are proposed:")
        for sql in alter_statements:
            print(sql)

    confirm = input("Do you want to apply these changes? (y/n): ")
    if confirm.lower() == "y":
        cursor = conn.cursor()

        for sql in new_tables_sql:
            try:
                cursor.execute(sql)
            except sqlite3.OperationalError as e:
                print(f"Could not execute: {sql}")
                print(e)

        for sql in alter_statements:
            try:
                cursor.execute(sql)
            except sqlite3.OperationalError as e:
                print(f"Could not execute: {sql}")
                print(e)

        conn.commit()
        print("Schema updated.")
    else:
        print("Schema update cancelled.")

    conn.close()


if __name__ == "__main__":
    main()
