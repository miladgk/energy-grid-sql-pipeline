-- =============================================================
-- 08_real_vs_synthetic_comparison.sql
-- Compares real Fingrid wind production data against the
-- synthetic generated wind readings on a daily scale.
-- Applies z-score standardization to normalize both series:
-- (value - AVG(value) OVER ()) / STDDEV(value) OVER ()
-- Computes the Pearson correlation coefficient using CORR().
-- =============================================================

WITH real_daily AS (
    SELECT DATE_TRUNC('day', recorded_at) AS day, 
           AVG(value) AS real_avg
    FROM grid_data
    WHERE metric = 'wind_production'
    GROUP BY 1
),
synthetic_daily AS (
    SELECT DATE_TRUNC('day', r.recorded_at) AS day, 
           AVG(r.value) AS synthetic_avg
    FROM readings r
    JOIN sensors s ON r.sensor_id = s.sensor_id
    JOIN facilities f ON s.facility_id = f.facility_id
    WHERE f.facility_type = 'wind' AND s.sensor_type = 'power_output'
    GROUP BY 1
),
daily_metrics AS (
    SELECT
        r.day,
        r.real_avg,
        s.synthetic_avg,
        (r.real_avg - AVG(r.real_avg) OVER ()) / NULLIF(STDDEV(r.real_avg) OVER (), 0) AS real_z,
        (s.synthetic_avg - AVG(s.synthetic_avg) OVER ()) / NULLIF(STDDEV(s.synthetic_avg) OVER (), 0) AS synthetic_z
    FROM real_daily r
    JOIN synthetic_daily s ON r.day = s.day
)
SELECT 
    TO_CHAR(day, 'YYYY-MM-DD') AS day_label,
    ROUND(real_avg::numeric, 4) AS real_avg,
    ROUND(synthetic_avg::numeric, 4) AS synthetic_avg,
    ROUND(real_z::numeric, 4) AS real_z,
    ROUND(synthetic_z::numeric, 4) AS synthetic_z,
    ROUND(CORR(synthetic_z, real_z) OVER ()::numeric, 4) AS correlation_coefficient
FROM daily_metrics
ORDER BY day;
