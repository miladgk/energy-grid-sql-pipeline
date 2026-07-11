-- =============================================================
-- 08_real_vs_synthetic_comparison.sql
-- Compares real Fingrid wind production data against the
-- synthetic generated wind readings, on a normalized
-- monthly scale (percentage of peak).
-- Computes the Pearson correlation coefficient to validate
-- whether the synthetic generator tracks real-world seasonality.
-- =============================================================

WITH real_monthly AS (
    SELECT DATE_TRUNC('month', recorded_at) AS month, 
           AVG(value) AS real_avg,
           MAX(AVG(value)) OVER() AS max_real_avg
    FROM grid_data
    WHERE metric = 'wind_production'
    GROUP BY 1
),
synthetic_monthly AS (
    SELECT DATE_TRUNC('month', r.recorded_at) AS month, 
           AVG(r.value) AS synthetic_avg,
           MAX(AVG(r.value)) OVER() AS max_synthetic_avg
    FROM readings r
    JOIN sensors s ON r.sensor_id = s.sensor_id
    JOIN facilities f ON s.facility_id = f.facility_id
    WHERE f.facility_type = 'wind' AND s.sensor_type = 'power_output'
    GROUP BY 1
)
SELECT 
    TO_CHAR(r.month, 'YYYY-MM') AS month_label,
    ROUND((r.real_avg / NULLIF(r.max_real_avg, 0) * 100)::numeric, 1) AS real_normalized_pct,
    ROUND((s.synthetic_avg / NULLIF(s.max_synthetic_avg, 0) * 100)::numeric, 1) AS synthetic_normalized_pct,
    ROUND(CORR(s.synthetic_avg, r.real_avg) OVER ()::numeric, 4) AS correlation_coefficient
FROM real_monthly r
JOIN synthetic_monthly s ON r.month = s.month
ORDER BY r.month;
