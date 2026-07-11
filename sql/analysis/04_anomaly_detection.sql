-- =============================================================
-- 04_anomaly_detection.sql
-- Statistical anomaly detection: z-score > 3 per sensor per month.
--
-- This is independent of the pre-labelled is_anomaly flag —
-- it detects outliers purely from the data distribution.
--
-- Techniques: multi-level CTEs, STDDEV(), ABS(), computed columns,
--             JOIN on composite key (sensor_id + month)
-- =============================================================

WITH sensor_monthly_stats AS (
    -- Step 1: compute baseline stats from clean (non-anomalous) readings only
    SELECT
        sensor_id,
        DATE_TRUNC('month', recorded_at)  AS month,
        AVG(value)                        AS mean_val,
        STDDEV(value)                     AS stddev_val
    FROM readings
    WHERE is_anomaly = FALSE
    GROUP BY
        sensor_id,
        DATE_TRUNC('month', recorded_at)
),
scored_readings AS (
    -- Step 2: score every reading against its sensor's monthly baseline
    SELECT
        r.reading_id,
        r.sensor_id,
        r.recorded_at,
        r.value,
        r.is_anomaly                        AS pre_labelled,
        s.mean_val,
        s.stddev_val,
        CASE
            WHEN s.stddev_val > 0
            THEN ABS(r.value - s.mean_val) / s.stddev_val
            ELSE 0
        END                                 AS z_score
    FROM readings r
    JOIN sensor_monthly_stats s
      ON  r.sensor_id = s.sensor_id
      AND DATE_TRUNC('month', r.recorded_at) = s.month
)
SELECT
    sr.reading_id,
    sr.sensor_id,
    sr.recorded_at,
    ROUND(sr.value::NUMERIC, 4)             AS value,
    ROUND(sr.z_score::NUMERIC, 2)           AS z_score,
    sr.pre_labelled                         AS was_flagged_in_source,
    f.facility_name,
    se.sensor_type,
    se.unit
FROM scored_readings sr
JOIN sensors    se ON sr.sensor_id   = se.sensor_id
JOIN facilities f  ON se.facility_id = f.facility_id
WHERE sr.z_score > 3
ORDER BY sr.z_score DESC
LIMIT 200;
