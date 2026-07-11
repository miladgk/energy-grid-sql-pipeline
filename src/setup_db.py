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

SCHEMA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "sql", "schema", "01_create_tables.sql"
)


def setup_schema(conn) -> None:
    """Execute 01_create_tables.sql against *conn*."""
    with open(SCHEMA_PATH, "r") as fh:
        sql = fh.read()

    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def main():
    print(f"Reading schema from: {os.path.abspath(SCHEMA_PATH)}")

    try:
        conn = get_connection()
    except Exception as exc:
        print(f"✗ Could not connect to database: {exc}")
        sys.exit(1)

    try:
        setup_schema(conn)
        print("✓ Schema created (or already exists — safe to re-run)")
    except Exception as exc:
        conn.rollback()
        print(f"✗ Schema setup failed: {exc}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
