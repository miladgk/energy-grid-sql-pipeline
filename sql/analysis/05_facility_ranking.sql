-- =============================================================
-- 05_facility_ranking.sql
-- Rank facilities by average power output efficiency
-- (actual output as % of nameplate capacity).
--
-- Techniques: RANK(), DENSE_RANK(), NTILE(), PERCENT_RANK(),
--             PARTITION BY for within-type ranking, multi-CTE
-- =============================================================

WITH monthly_output AS (
    -- Step 1: average hourly output per facility per month
    SELECT
        f.facility_id,
        f.facility_name,
        f.facility_type,
        f.capacity_mw,
        f.country,
        DATE_TRUNC('month', r.recorded_at)   AS month,
        AVG(r.value)                          AS avg_output_mw
    FROM readings r
    JOIN sensors    s ON r.sensor_id   = s.sensor_id
    JOIN facilities f ON s.facility_id = f.facility_id
    WHERE s.sensor_type = 'power_output'
      AND r.is_anomaly  = FALSE
    GROUP BY
        f.facility_id, f.facility_name, f.facility_type,
        f.capacity_mw, f.country,
        DATE_TRUNC('month', r.recorded_at)
),
efficiency AS (
    -- Step 2: collapse to a single annual efficiency figure per facility
    SELECT
        facility_id,
        facility_name,
        facility_type,
        country,
        capacity_mw,
        ROUND(
            AVG(avg_output_mw / NULLIF(capacity_mw, 0) * 100)::NUMERIC,
            2
        )                                     AS avg_efficiency_pct
    FROM monthly_output
    GROUP BY
        facility_id, facility_name, facility_type, country, capacity_mw
)
SELECT
    facility_name,
    facility_type,
    country,
    capacity_mw,
    avg_efficiency_pct,

    -- Global rank across all facility types
    RANK()       OVER (ORDER BY avg_efficiency_pct DESC)             AS overall_rank,

    -- Rank within each facility type (wind vs solar vs substation)
    RANK()       OVER (
                     PARTITION BY facility_type
                     ORDER BY avg_efficiency_pct DESC
                 )                                                   AS rank_within_type,

    -- Performance quartile: 1 = top 25%, 4 = bottom 25%
    NTILE(4)     OVER (ORDER BY avg_efficiency_pct DESC)             AS performance_quartile,

    -- Percentile score (0–100): what % of facilities does this one outperform?
    ROUND(
        PERCENT_RANK() OVER (ORDER BY avg_efficiency_pct)::NUMERIC * 100,
        1
    )                                                                AS percentile

FROM efficiency
ORDER BY overall_rank;
