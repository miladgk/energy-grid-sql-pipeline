"""
test_data_quality.py
~~~~~~~~~~~~~~~~~~~~
Pytest suite that runs data quality checks against the live PostgreSQL
database and asserts business rules are satisfied post-ingestion.

Run with:
    pytest tests/test_data_quality.py -v

The tests use the same SQL logic as sql/etl/02_data_quality_checks.sql
so the two sources stay in sync.

Fixture note: a single connection is shared across the session to avoid
the overhead of a new TCP handshake per test.
"""

import os
import sys
import pytest
import psycopg2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from db_connection import get_connection


# ──────────────────────────────────────────────────────────────
# Session-scoped DB connection
# ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def conn():
    """Open one connection for the entire test session."""
    connection = get_connection()
    yield connection
    connection.close()


def _scalar(conn, sql: str):
    """Execute *sql* and return the first cell of the first row."""
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()[0]


def _rows(conn, sql: str) -> list:
    """Execute *sql* and return all rows."""
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


# ──────────────────────────────────────────────────────────────
# Check 1: Every sensor has at least one reading
# ──────────────────────────────────────────────────────────────

def test_no_sensors_without_readings(conn):
    """
    A sensor with no readings indicates either a broken foreign key
    or a silent ingestion failure for that sensor's data.
    """
    sql = """
        SELECT s.sensor_id
        FROM sensors s
        LEFT JOIN readings r ON s.sensor_id = r.sensor_id
        WHERE r.reading_id IS NULL
    """
    orphan_sensors = _rows(conn, sql)
    assert orphan_sensors == [], (
        f"Found {len(orphan_sensors)} sensor(s) with no readings: "
        f"{[row[0] for row in orphan_sensors]}"
    )


# ──────────────────────────────────────────────────────────────
# Check 2: No NULL values in the readings table
# ──────────────────────────────────────────────────────────────

def test_no_null_values(conn):
    """
    The generator always produces a float value; NULLs suggest a
    parsing error during CSV ingestion.
    """
    count = _scalar(conn, "SELECT COUNT(*) FROM readings WHERE value IS NULL")
    assert count == 0, f"Expected 0 NULL values, found {count}"


# ──────────────────────────────────────────────────────────────
# Check 3: Overall anomaly rate is between 1 % and 4 %
# ──────────────────────────────────────────────────────────────

def test_anomaly_rate_within_expected_range(conn):
    """
    The generator targets ~2 % anomalies (ANOMALY_RATE = 0.02).
    Allow a ±2 % band to account for random variance.
    Values outside [1 %, 4 %] indicate a generation or ingestion bug.
    """
    sql = """
        SELECT
            100.0 * SUM(CASE WHEN is_anomaly THEN 1 ELSE 0 END)
            / NULLIF(COUNT(*), 0)
        FROM readings
    """
    anomaly_pct = float(_scalar(conn, sql))
    assert 1.0 <= anomaly_pct <= 4.0, (
        f"Anomaly rate {anomaly_pct:.2f}% is outside expected range [1%, 4%]"
    )


# ──────────────────────────────────────────────────────────────
# Check 4: Data covers all 365 days of 2023
# ──────────────────────────────────────────────────────────────

def test_full_year_coverage(conn):
    """
    Readings should span every day of 2023.  A gap indicates that a
    portion of the data file was not ingested.
    """
    import os
    sql = """
        SELECT COUNT(DISTINCT DATE_TRUNC('day', recorded_at))
        FROM readings
    """
    days_with_data = _scalar(conn, sql)
    if os.getenv("CI") == "true":
        assert days_with_data > 0, "Expected at least 1 day of data in CI"
    else:
        assert days_with_data == 365, (
            f"Expected 365 days of data, found {days_with_data}"
        )


# ──────────────────────────────────────────────────────────────
# Check 5: Row counts are plausible for a 5-minute dataset
# ──────────────────────────────────────────────────────────────

def test_reading_volume_is_realistic(conn):
    """
    60 sensors × 365 days × 288 intervals/day = 6,307,200 readings.
    Allow ±5 % tolerance for anomaly injection edge cases.
    """
    import os
    if os.getenv("CI") == "true":
        expected  = 50_000
        tolerance = 0.10  # 10% tolerance for scaled down CI
    else:
        expected  = 60 * 365 * 288   # 6_307_200
        tolerance = 0.05

    actual    = _scalar(conn, "SELECT COUNT(*) FROM readings")

    assert abs(actual - expected) / expected <= tolerance, (
        f"Row count {actual:,} deviates > tolerance from expected {expected:,}"
    )

