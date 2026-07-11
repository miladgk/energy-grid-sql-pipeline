"""
run_quality_checks.py
~~~~~~~~~~~~~~~~~~~~~
Reads sql/etl/02_data_quality_checks.sql, splits it into individual
queries, executes each one, and prints the results as formatted tables.

This script serves two purposes:
  1. A human-readable post-ingestion sanity check you can run manually
     and paste output from into a README or share with a reviewer.
  2. It is called automatically at the end of ingest.py so data quality
     is always verified immediately after a load.

Usage (standalone):
    python src/run_quality_checks.py

Exit codes:
    0 — all checks passed
    1 — one or more checks found problems (non-zero row counts where
        zero is expected, or coverage below 365 days)
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from db_connection import get_connection

CHECKS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "sql", "etl", "02_data_quality_checks.sql"
)

DAYS_EXPECTED = int(os.getenv("DAYS_EXPECTED", 365))

# Human-readable labels for each check block, in order
CHECK_LABELS = [
    "Check 1 — Sensors with no readings (expect 0 rows)",
    "Check 2 — Readings with NULL values  (expect count = 0)",
    "Check 3 — Anomaly rate per facility  (expect ~2%)",
    f"Check 4 — Timestamp coverage         (expect >= {DAYS_EXPECTED} days)",
]

# For each check, define the failure condition as a callable
# that receives the resulting DataFrame and returns True if the check FAILS.
FAILURE_CONDITIONS = [
    lambda df: len(df) > 0,                                        # Check 1: any orphan sensors
    lambda df: int(df.iloc[0, 0]) > 0,                            # Check 2: any NULLs
    lambda df: False,                                              # Check 3: informational only
    lambda df: int(df["days_with_data"].iloc[0]) < DAYS_EXPECTED,  # Check 4: missing days
]



def _split_sql_file(path: str) -> list[str]:
    """
    Split a SQL file into individual statements by splitting on lines
    that start with '-- Check'.  Returns one string per check block,
    with the leading comment included so output is self-documenting.
    """
    with open(path, "r") as fh:
        raw = fh.read()

    # Split on the separator comments (keep the delimiter with the block)
    import re
    blocks = re.split(r"(?=-- -{10,})", raw)

    # Each real check block starts with '-- Check' somewhere inside it
    queries = []
    for block in blocks:
        # Strip the dashed separator line, keep only the SQL + comment
        lines = [ln for ln in block.splitlines() if not ln.strip().startswith("-- -")]
        cleaned = "\n".join(lines).strip()
        if not cleaned:
            continue
        # Only include blocks that contain a SELECT statement
        if "SELECT" in cleaned.upper():
            queries.append(cleaned)

    return queries


def run_quality_checks(conn) -> bool:
    """
    Execute all checks in 02_data_quality_checks.sql.

    Returns True if all checks pass, False if any check detects a problem.
    """
    queries = _split_sql_file(CHECKS_PATH)

    all_passed = True
    print("\n" + "=" * 60)
    print("DATA QUALITY REPORT")
    print("=" * 60)

    for i, (label, sql, is_failure) in enumerate(
        zip(CHECK_LABELS, queries, FAILURE_CONDITIONS)
    ):
        print(f"\n{label}")
        print("-" * 60)
        try:
            df = pd.read_sql_query(sql, conn)
            print(df.to_string(index=False) if not df.empty else "  (no rows returned)")

            if is_failure(df):
                print("  ✗ FAILED — see results above")
                all_passed = False
            else:
                print("  ✓ Passed")
        except Exception as exc:
            print(f"  ✗ ERROR executing check {i + 1}: {exc}")
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("All quality checks passed.")
    else:
        print("One or more quality checks FAILED — review output above.")
    print("=" * 60 + "\n")

    return all_passed


def main():
    try:
        conn = get_connection()
    except Exception as exc:
        print(f"✗ Could not connect to database: {exc}")
        sys.exit(1)

    try:
        passed = run_quality_checks(conn)
    finally:
        conn.close()

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
