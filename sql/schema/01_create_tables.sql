-- =============================================================
-- 01_create_tables.sql
-- Energy Analytics Platform — Database Schema
--
-- Design notes:
--   • "timestamp" is a reserved SQL keyword and a PostgreSQL type.
--     The readings table uses "recorded_at" instead to avoid
--     ambiguity in ORMs and query parsers.
--   • Indexes on recorded_at and sensor_id support the heavy
--     time-range and join patterns used in the analysis queries.
-- =============================================================

CREATE TABLE IF NOT EXISTS facilities (
    facility_id       SERIAL PRIMARY KEY,
    facility_name     VARCHAR(100) NOT NULL,
    facility_type     VARCHAR(50)  NOT NULL
                          CHECK (facility_type IN ('wind', 'solar', 'substation')),
    country           VARCHAR(50)  NOT NULL,
    capacity_mw       NUMERIC(8,2) NOT NULL,
    commissioned_year SMALLINT     NOT NULL
);

CREATE TABLE IF NOT EXISTS sensors (
    sensor_id    SERIAL PRIMARY KEY,
    facility_id  INT         NOT NULL REFERENCES facilities(facility_id),
    sensor_type  VARCHAR(50) NOT NULL,
    unit         VARCHAR(20) NOT NULL
);

CREATE TABLE IF NOT EXISTS readings (
    reading_id   BIGSERIAL    PRIMARY KEY,
    sensor_id    INT          NOT NULL REFERENCES sensors(sensor_id),
    recorded_at  TIMESTAMPTZ  NOT NULL,   -- named recorded_at, not "timestamp"
    value        NUMERIC(10,4),
    is_anomaly   BOOLEAN      DEFAULT FALSE
);

-- Composite index covers the most common query pattern:
--   WHERE sensor_id = ? AND recorded_at BETWEEN ? AND ?
CREATE INDEX IF NOT EXISTS idx_readings_sensor_time ON readings(sensor_id, recorded_at);

