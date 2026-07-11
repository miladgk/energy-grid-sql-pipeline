"""
api.py
~~~~~~
A lightweight FastAPI service that serves the engineered data over HTTP.
This transforms the project from a "collection of scripts" into a
deployable data product.

Endpoints
---------
GET /api/anomalies
    Returns statistical anomalies (z-score > threshold) detected in the
    readings table, with optional query parameters for filtering.

GET /api/facilities/ranking
    Returns all facilities ranked by average power efficiency.

GET /health
    Simple liveness check.

Usage
-----
    uvicorn src.api:app --reload --port 8000

Then open:  http://localhost:8000/docs  (auto-generated Swagger UI)
"""

import os
import sys
from typing import Optional

import psycopg2.extras
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(__file__))
from db_connection import get_connection


app = FastAPI(
    title="Energy Facility Analytics API",
    description=(
        "Serves operational analytics from the energy facility "
        "PostgreSQL database."
    ),
    version="1.0.0",
)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _fetch_rows(sql: str, params: tuple = ()) -> list[dict]:
    """Execute *sql* and return all rows as a list of dicts."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"])
def health_check():
    """Liveness probe — returns 200 if the API process is running."""
    return {"status": "ok"}


@app.get("/api/anomalies", tags=["analytics"])
def get_anomalies(
    z_threshold: float = Query(
        default=3.0,
        ge=1.0,
        le=10.0,
        description="Z-score threshold above which a reading is flagged as anomalous.",
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of anomalies to return.",
    ),
    facility_type: Optional[str] = Query(
        default=None,
        description="Filter by facility type: 'wind', 'solar', or 'substation'.",
    ),
):
    """
    Return statistical anomalies detected via z-score analysis.

    A reading is considered anomalous when its value deviates more than
    *z_threshold* standard deviations from that sensor's monthly mean,
    calculated using only non-flagged (clean) readings as the baseline.
    """
    type_filter = "AND f.facility_type = %s" if facility_type else ""
    params: tuple = (facility_type,) if facility_type else ()

    sql = f"""
        WITH sensor_monthly_stats AS (
            SELECT
                sensor_id,
                DATE_TRUNC('month', recorded_at)  AS month,
                AVG(value)                        AS mean_val,
                STDDEV(value)                     AS stddev_val
            FROM readings
            WHERE is_anomaly = FALSE
            GROUP BY sensor_id, DATE_TRUNC('month', recorded_at)
        ),
        scored AS (
            SELECT
                r.reading_id,
                r.sensor_id,
                r.recorded_at,
                r.value,
                r.is_anomaly                         AS pre_labelled,
                CASE
                    WHEN s.stddev_val > 0
                    THEN ABS(r.value - s.mean_val) / s.stddev_val
                    ELSE 0
                END                                  AS z_score,
                f.facility_name,
                f.facility_type,
                se.sensor_type,
                se.unit
            FROM readings r
            JOIN sensor_monthly_stats s
              ON  r.sensor_id = s.sensor_id
              AND DATE_TRUNC('month', r.recorded_at) = s.month
            JOIN sensors    se ON r.sensor_id    = se.sensor_id
            JOIN facilities f  ON se.facility_id = f.facility_id
            WHERE 1=1 {type_filter}
        )
        SELECT *
        FROM scored
        WHERE z_score > %s
        ORDER BY z_score DESC
        LIMIT %s
    """

    try:
        rows = _fetch_rows(sql, params + (z_threshold, limit))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Convert Decimal / datetime to JSON-serialisable types
    for row in rows:
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                row[k] = v.isoformat()
            elif hasattr(v, "__float__"):
                row[k] = float(v)

    return {
        "z_threshold"    : z_threshold,
        "facility_type"  : facility_type,
        "count"          : len(rows),
        "anomalies"      : rows,
    }


@app.get("/api/facilities/ranking", tags=["analytics"])
def get_facility_ranking():
    """
    Return all facilities ranked by annual average power output efficiency
    (actual output as % of nameplate capacity).
    """
    sql = """
        WITH monthly_output AS (
            SELECT
                f.facility_id,
                f.facility_name,
                f.facility_type,
                f.capacity_mw,
                f.country,
                AVG(r.value)   AS avg_output_mw
            FROM readings r
            JOIN sensors    s ON r.sensor_id   = s.sensor_id
            JOIN facilities f ON s.facility_id = f.facility_id
            WHERE s.sensor_type = 'power_output'
              AND r.is_anomaly  = FALSE
            GROUP BY
                f.facility_id, f.facility_name, f.facility_type,
                f.capacity_mw, f.country
        )
        SELECT
            facility_name,
            facility_type,
            country,
            ROUND(capacity_mw::NUMERIC, 2)                              AS capacity_mw,
            ROUND((avg_output_mw / NULLIF(capacity_mw, 0) * 100)::NUMERIC, 2)
                                                                        AS avg_efficiency_pct,
            RANK() OVER (ORDER BY avg_output_mw / NULLIF(capacity_mw, 0) DESC)
                                                                        AS overall_rank
        FROM monthly_output
        ORDER BY overall_rank
    """

    try:
        rows = _fetch_rows(sql)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    for row in rows:
        for k, v in row.items():
            if hasattr(v, "__float__"):
                row[k] = float(v)

    return {"count": len(rows), "facilities": rows}
