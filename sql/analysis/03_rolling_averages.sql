-- =============================================================
-- 03_rolling_averages.sql
-- 24-hour rolling average of power output per facility.
--
-- Techniques: CTEs, AVG() OVER with ROWS BETWEEN frame,
--             PARTITION BY, DATE_TRUNC
-- =============================================================

WITH hourly_power AS (
    -- Collapse 5-minute readings to hourly averages first,
    -- so the rolling window frame of 23 PRECEDING = exactly 24 hours.
    SELECT
        f.facility_id,
        f.facility_name,
        DATE_TRUNC('hour', r.recorded_at)  AS hour,
        AVG(r.value)                       AS avg_power_mw
    FROM readings r
    JOIN sensors    s ON r.sensor_id   = s.sensor_id
    JOIN facilities f ON s.facility_id = f.facility_id
    WHERE s.sensor_type = 'power_output'
      AND r.is_anomaly  = FALSE
    GROUP BY
        f.facility_id,
        f.facility_name,
        DATE_TRUNC('hour', r.recorded_at)
)
SELECT
    facility_name,
    hour,
    ROUND(avg_power_mw::NUMERIC, 4)        AS avg_power_mw,
    ROUND(
        AVG(avg_power_mw) OVER (
            PARTITION BY facility_id
            ORDER BY hour
            ROWS BETWEEN 23 PRECEDING AND CURRENT ROW
        )::NUMERIC, 4
    )                                       AS rolling_24h_avg_mw
FROM hourly_power
ORDER BY facility_name, hour;
