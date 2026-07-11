"""
ingest_grid_data.py
~~~~~~~~~~~~~~~~~~~
Loads grid_data.csv into PostgreSQL.
Uses chunking, transactions with rollback, and ON CONFLICT DO NOTHING for idempotence.
"""

import os
import sys
import pandas as pd
import psycopg2
from psycopg2.extensions import connection as PgConnection

CHUNK_SIZE = 5_000

_INSERT_GRID_DATA = """
    INSERT INTO grid_data (dataset_id, country, recorded_at, value, metric)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (dataset_id, recorded_at) DO NOTHING
"""

def ingest_grid_data(conn: PgConnection, filepath: str, chunk_size: int = CHUNK_SIZE) -> None:
    """Load grid_data.csv into the grid_data table in chunks."""
    total_rows = 0
    chunk_num = 0

    try:
        reader = pd.read_csv(
            filepath,
            chunksize=chunk_size,
            parse_dates=["recorded_at"],
        )
        for chunk in reader:
            chunk_num += 1
            rows = [
                (
                    int(r.dataset_id),
                    r.country,
                    r.recorded_at.isoformat(),
                    float(r.value),
                    r.metric,
                )
                for r in chunk.itertuples(index=False)
            ]
            with conn.cursor() as cur:
                cur.executemany(_INSERT_GRID_DATA, rows)
            conn.commit()
            total_rows += len(rows)

            if chunk_num % 50 == 0:
                print(f"    … {total_rows:>10,} grid rows loaded so far")

    except Exception as exc:
        conn.rollback()
        raise RuntimeError(f"ingest_grid_data failed at chunk {chunk_num}: {exc}") from exc

    print(f"  ✓ grid_data : {total_rows:,} rows inserted across {chunk_num} chunks (or skipped if already present)")


def main():
    sys.path.insert(0, os.path.dirname(__file__))
    from db_connection import get_connection

    raw_dir = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
    csv_path = os.path.join(raw_dir, "grid_data.csv")

    if not os.path.exists(csv_path):
        print(f"✗ Grid data CSV file not found at: {os.path.abspath(csv_path)}")
        print("Please run 'python src/fetch_grid_data.py' first to generate the file.")
        sys.exit(1)

    print("Connecting to PostgreSQL …")
    try:
        conn = get_connection()
        print("  ✓ Connected\n")
    except Exception as exc:
        print(f"✗ Could not connect to database: {exc}")
        sys.exit(1)

    print("Ingesting grid data …")
    try:
        ingest_grid_data(conn, csv_path)
        print("\nIngestion completed successfully.")
    except Exception as exc:
        print(f"\n✗ Ingestion failed: {exc}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
