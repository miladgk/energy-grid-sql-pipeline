"""
setup_db.py
~~~~~~~~~~~
Reads sql/schema/01_create_tables.sql and executes it against the
configured PostgreSQL database.

Use this when:
  • You are NOT using Docker Compose (bare-metal Postgres install), OR
  • You need to reset the schema without rebuilding the Docker container
    (e.g. after a docker volume rm to wipe all data).

Usage:
    python src/setup_db.py

The script is idempotent — every CREATE TABLE and CREATE INDEX uses
IF NOT EXISTS, so running it on an already-configured database is safe.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from db_connection import get_connection

import glob

SCHEMA_DIR = os.path.join(
    os.path.dirname(__file__), "..", "sql", "schema"
)


def setup_schema(conn) -> None:
    """Execute all .sql files in sql/schema/ in sorted alphabetical order against *conn*."""
    sql_files = sorted(glob.glob(os.path.join(SCHEMA_DIR, "*.sql")))
    if not sql_files:
        print("No schema SQL files found.")
        return

    with conn.cursor() as cur:
        for filepath in sql_files:
            filename = os.path.basename(filepath)
            print(f"Applying schema file: {filename}")
            with open(filepath, "r") as fh:
                sql = fh.read()
            cur.execute(sql)
    conn.commit()


def main():
    print(f"Scanning schema directory: {os.path.abspath(SCHEMA_DIR)}")

    try:
        conn = get_connection()
    except Exception as exc:
        print(f"✗ Could not connect to database: {exc}")
        sys.exit(1)

    try:
        setup_schema(conn)
        print("✓ All schema scripts applied successfully (or already exists)")
    except Exception as exc:
        conn.rollback()
        print(f"✗ Schema setup failed: {exc}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
