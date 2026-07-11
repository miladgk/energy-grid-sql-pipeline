-- =============================================================
-- 06_monthly_report.sql
-- Monthly summary: output, anomaly rate, month-over-month change.
--
-- Techniques: GROUP BY + FILTER aggregation, LAG() for MoM delta,
--             CASE for severity banding, NULLIF for safe division,
--             TO_CHAR for formatted month label
-- =============================================================

WITH monthly_summary AS (
    SELECT
        f.country,
        f.facility_type,
        DATE_TRUNC('month', r.recorded_at)                              AS month,
        COUNT(DISTINCT f.facility_id)                                   AS active_facilities,
        ROUND(AVG(r.value)::NUMERIC,  3)                                AS avg_power_mw,
        ROUND(SUM(r.value)::NUMERIC,  1)                                AS total_energy_mwh,
        COUNT(*) FILTER (WHERE r.is_anomaly = TRUE)                     AS anomaly_count,
        COUNT(*)                                                        AS total_readings,
        ROUND(
            100.0
            * COUNT(*) FILTER (WHERE r.is_anomaly = TRUE)
            / NULLIF(COUNT(*), 0),
            2
        )                                                               AS anomaly_rate_pct
    FROM readings r
    JOIN sensors    s ON r.sensor_id   = s.sensor_id
    JOIN facilities f ON s.facility_id = f.facility_id
    WHERE s.sensor_type = 'power_output'
    GROUP BY
        f.country,
        f.facility_type,
        DATE_TRUNC('month', r.recorded_at)
)
SELECT
    country,
    facility_type,
    TO_CHAR(month, 'YYYY-MM')                                           AS month,
    active_facilities,
    avg_power_mw,
    total_energy_mwh,
    anomaly_count,
    anomaly_rate_pct,

    -- Month-over-month energy delta
    ROUND(
        (
            total_energy_mwh
            - LAG(total_energy_mwh) OVER (
                  PARTITION BY country, facility_type
                  ORDER BY month
              )
        )::NUMERIC,
        1
    )                                                                   AS mom_energy_change_mwh,

    -- Human-readable anomaly severity band
    CASE
        WHEN anomaly_rate_pct > 3.0  THEN 'HIGH'
        WHEN anomaly_rate_pct > 1.5  THEN 'MEDIUM'
        ELSE                              'LOW'
    END                                                                 AS anomaly_severity

FROM monthly_summary
ORDER BY country, facility_type, month;
