import sqlite3
import os

def get_db_connection():
    """Establishes a connection to the database."""
    db_path = os.path.join(os.path.dirname(__file__), 'jbot.db')
    return sqlite3.connect(db_path)

def get_current_schema(conn):
    """Retrieves the current schema from the database."""
    cursor = conn.cursor()
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    return [row[0] for row in cursor.fetchall()]

def get_target_schema():
    """Reads the target schema from the schema.sql file."""
    schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
    with open(schema_path, 'r') as f:
        return f.read()

def parse_schema(schema_sql):
    """Parses CREATE TABLE statements and returns a dictionary of table_name: statement."""
    statements = [s.strip() for s in schema_sql.strip().split(';') if s.strip()]
    schema_dict = {}
    for statement in statements:
        if 'CREATE TABLE' in statement:
            # This parsing is simplistic and might need to be more robust
            try:
                table_name = statement.split('IF NOT EXISTS ')[1].split(' (')[0].strip()
                # Normalize by removing comments and standardizing whitespace
                normalized_statement = ' '.join(line.strip() for line in statement.splitlines() if not line.strip().startswith('--'))
                normalized_statement = ' '.join(normalized_statement.split()).replace("IF NOT EXISTS ", "")
                schema_dict[table_name] = normalized_statement
            except IndexError:
                # Handle cases without 'IF NOT EXISTS'
                try:
                    table_name = statement.split('CREATE TABLE ')[1].split(' (')[0].strip()
                    normalized_statement = ' '.join(line.strip() for line in statement.splitlines() if not line.strip().startswith('--'))
                    normalized_statement = ' '.join(normalized_statement.split())
                    schema_dict[table_name] = normalized_statement
                except IndexError:
                    print(f"Warning: Could not parse table name from: {statement}")
    return schema_dict

def compare_schemas(current_schema_list, target_schema_sql):
    """
    Compares the current and target schemas and returns the differences.
    """
    current_schema_sql = ';\n'.join(current_schema_list)
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
                    'current': current_statement,
                    'target': target_statement
                }

    return new_tables, modified_tables


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
            table_name = schema.split('CREATE TABLE')[1].lstrip().split('(')[0].strip()
            current_tables.add(table_name)
        except IndexError:
            continue

    # Get target table names and their CREATE statements
    target_statements = [s.strip() for s in target_schema_sql.strip().split(';') if s.strip()]
    
    new_tables_sql = []
    for statement in target_statements:
        if 'CREATE TABLE' in statement:
            try:
                table_name_part = statement.split('CREATE TABLE')[1]
                if 'IF NOT EXISTS' in table_name_part:
                    table_name = table_name_part.split('IF NOT EXISTS')[1].split('(')[0].strip()
                else:
                    table_name = table_name_part.split('(')[0].strip()
                
                if table_name not in current_tables:
                    new_tables_sql.append(statement + ';')
            except IndexError:
                print(f"Warning: Could not parse statement: {statement}")

    # TODO: Implement ALTER TABLE for modified tables to avoid data loss.
    # The current implementation only handles new tables.

    if not new_tables_sql:
        print("Database schema is up to date.")
        conn.close()
        return

    print("The following new tables are proposed:")
    for sql in new_tables_sql:
        print(sql)
        
    confirm = input("Do you want to apply these changes? (y/n): ")
    if confirm.lower() == 'y':
        cursor = conn.cursor()
        for sql in new_tables_sql:
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


if __name__ == '__main__':
    main()
