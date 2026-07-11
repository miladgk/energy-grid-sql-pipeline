-- =============================================================
-- 07_add_grid_data.sql
-- Creates the grid_data table for actual Fingrid open data metrics.
-- =============================================================

CREATE TABLE IF NOT EXISTS grid_data (
    id SERIAL PRIMARY KEY,
    dataset_id INTEGER NOT NULL,
    country VARCHAR(2) NOT NULL DEFAULT 'FI',
    recorded_at TIMESTAMPTZ NOT NULL,
    value NUMERIC(12,4) NOT NULL,
    metric VARCHAR(50) NOT NULL,
    CONSTRAINT uq_grid_data_dataset_time UNIQUE (dataset_id, recorded_at)
);

-- Index for comparison queries (metric lookups over time ranges)
CREATE INDEX IF NOT EXISTS idx_grid_data_metric_time ON grid_data (metric, recorded_at);
