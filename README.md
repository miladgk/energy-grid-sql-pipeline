# Energy Facility Performance & Anomaly Analytics Platform

[![CI Pipeline](https://github.com/miladgk/energy-grid-sql-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/miladgk/energy-grid-sql-pipeline/actions/workflows/ci.yml)

A local data engineering project that ingests, transforms, and analyses
operational time-series data from a fictional network of 20 industrial energy
facilities (wind farms, solar plants, substations) across Scandinavia.
The project demonstrates a production-oriented pipeline: synthetic data
generation → PostgreSQL (Docker) → chunked Python ingestion → advanced SQL
analysis → automated CSV reporting → FastAPI JSON endpoint.

---

## Architecture

```
┌─────────────────────┐
│  generate_data.py   │  Creates ~6.3 M synthetic rows
│  (Pandas + NumPy)   │  at 5-minute resolution
└────────┬────────────┘
         │  data/raw/*.csv
         ▼
┌─────────────────────┐
│    ingest.py        │  Chunked loading (5 k rows/batch)
│    (psycopg2)       │  ON CONFLICT DO NOTHING — idempotent
└────────┬────────────┘
         │  SQL COPY
         ▼
┌─────────────────────────────────────────────────────┐
│              PostgreSQL 15  (Docker)                │
│                                                     │
│   facilities ──< sensors ──< readings               │
│                              (6.3 M rows, indexed)  │
└──────┬───────────────────────────────┬──────────────┘
       │  pandas.read_sql_query        │  psycopg2
       ▼                               ▼
┌─────────────────┐          ┌──────────────────────┐
│  run_report.py  │          │       api.py         │
│  SQL → CSV      │          │  FastAPI  :8000      │
│  outputs/*.csv  │          │  GET /api/anomalies  │
└─────────────────┘          └──────────────────────┘
```

---

## Tech Stack

| Layer         | Technology                          |
|---------------|-------------------------------------|
| Database      | PostgreSQL 15 (Docker Compose)      |
| Language      | Python 3.11                         |
| DB connector  | psycopg2                            |
| Data wrangling| pandas, NumPy                       |
| API           | FastAPI + Uvicorn                   |
| Testing       | pytest                              |
| Environment   | Conda                               |

---

## Project Structure

```
energy-analytics-sql/
│
├── docker-compose.yml          # PostgreSQL 15 containerised — one command setup
├── environment.yaml            # Conda environment
├── config_template.yaml        # DB credentials template (config.yaml is git-ignored)
├── .gitignore
├── README.md
│
├── data/
│   ├── raw/                    # Generated CSVs (git-ignored due to size)
│   └── processed/              # Optional hand-crafted exports
│
├── sql/
│   ├── schema/
│   │   └── 01_create_tables.sql
│   ├── etl/
│   │   └── 02_data_quality_checks.sql
│   └── analysis/
│       ├── 03_rolling_averages.sql
│       ├── 04_anomaly_detection.sql
│       ├── 05_facility_ranking.sql
│       └── 06_monthly_report.sql
│
├── src/
│   ├── setup_db.py             # Runs 01_create_tables.sql (fallback for non-Docker setups)
│   ├── generate_data.py        # Synthetic data generator
│   ├── db_connection.py        # Credential-safe psycopg2 factory
│   ├── ingest.py               # Chunked CSV → PostgreSQL pipeline
│   ├── run_quality_checks.py   # Runs 02_data_quality_checks.sql, prints results
│   ├── run_report.py           # Runs all analysis SQL → timestamped CSVs
│   └── api.py                  # FastAPI service (anomalies, rankings)
│
├── tests/
│   └── test_data_quality.py    # pytest suite for post-ingestion assertions
│
└── outputs/                    # Auto-generated report CSVs land here
```

---

## Setup Instructions

### 1 — Clone and create the Conda environment

```bash
git clone https://github.com/miladgk/energy-grid-sql-pipeline.git
cd energy-grid-sql-pipeline

conda env create -f environment.yaml
conda activate energy-analytics
```

> [!NOTE]
> **Python-only setup:** If you are not using Conda, you can create a virtual environment and install the pinned dependencies using pip:
> ```bash
> pip install -r requirements.txt
> ```


### 2 — Start PostgreSQL with Docker Compose

```bash
docker-compose up -d
```

This spins up a PostgreSQL 15 container on `localhost:5432` and
automatically runs `sql/schema/01_create_tables.sql` on first boot
(via the `docker-entrypoint-initdb.d` mount).

To verify it is healthy:

```bash
docker-compose ps
# State should show "healthy"
```

> **Non-Docker / schema reset:** If you are using a bare-metal Postgres
> install, or you need to reset the schema after a `docker volume rm`,
> run the schema script manually:
>
> ```bash
> python src/setup_db.py
> ```
>
> This reads and executes `sql/schema/01_create_tables.sql` directly.
> It is idempotent — safe to re-run on an existing database.

### 3 — Configure database credentials

```bash
cp config_template.yaml config.yaml
```

Edit `config.yaml` with the credentials from `docker-compose.yml`:

```yaml
database:
  host: localhost
  port: 5432
  dbname: energy_analytics
  user: admin
  password: password
```

> `config.yaml` is in `.gitignore` and is **never committed**.

### 4 — Generate synthetic data

```bash
python src/generate_data.py
```

This writes ~6.3 million rows to `data/raw/readings.csv` (and the two
smaller files). Expect ~45 seconds on a modern laptop.

### 5 — Ingest into PostgreSQL

```bash
python src/ingest.py
```

Reads each CSV in 5,000-row chunks and bulk-inserts into PostgreSQL.
Expect 3–8 minutes for the full readings table.

`ingest.py` automatically calls `run_quality_checks.py` when it
finishes, so `02_data_quality_checks.sql` is always executed immediately
after a load. The process exits with code `1` if any check fails.

### 6 — Run data quality checks (standalone)

The quality checks also run independently at any time:

```bash
python src/run_quality_checks.py
```

This executes `sql/etl/02_data_quality_checks.sql` and prints a
formatted table for each of the four checks. It exits with code `1` if
any check detects a problem, making it usable as a CI gate.

### 7 — Run pytest assertions

```bash
pytest tests/test_data_quality.py -v
```

All five assertions should pass:

- No sensors without readings
- Zero NULL values
- Anomaly rate in [1 %, 4 %]
- 365 days of coverage
- Row count within 5 % of 6,307,200

### 8 — Run the analysis report

```bash
python src/run_report.py
```

Executes the four analysis SQL files in order and writes timestamped
CSVs to `outputs/`.

### 9 — Start the API

```bash
uvicorn src.api:app --reload --port 8000
```

Open `http://localhost:8000/docs` for the auto-generated Swagger UI.

---

## SQL Techniques Demonstrated

| Technique | Where |
|---|---|
| **CTEs** (`WITH` clauses) | All analysis files — multi-step transformations broken into readable named steps |
| **Window functions** (`AVG OVER`, `ROWS BETWEEN`) | `03_rolling_averages.sql` — 24-hour trailing average per facility |
| **`RANK()`, `DENSE_RANK()`, `NTILE()`, `PERCENT_RANK()`** | `05_facility_ranking.sql` — global rank, within-type rank, performance quartile |
| **`LAG()` for time-series** | `06_monthly_report.sql` — month-over-month energy change |
| **Z-score anomaly detection** | `04_anomaly_detection.sql` — statistical outlier detection via `STDDEV()` and CTE pipeline |
| **`FILTER` aggregation** | `02_data_quality_checks.sql`, `06_monthly_report.sql` — conditional counts without subqueries |
| **`NULLIF` for safe division** | `05_facility_ranking.sql`, `06_monthly_report.sql` — prevents division-by-zero |
| **`DATE_TRUNC` + `TO_CHAR`** | All analysis files — period aggregation and formatted output |
| **Composite indexes** | Schema — `(sensor_id, recorded_at)` index cuts query execution time from 13.4ms to 0.36ms (97.3% reduction). See [index_benchmark.md](file:///mnt/d/Projects/sql_docker/energy-analytics-sql/benchmarks/index_benchmark.md) for execution plans. |
| **`ON CONFLICT DO NOTHING`** | `ingest.py` — idempotent ingestion; safe to re-run the pipeline |

---

## Sample Output — Facility Ranking (05)

```
facility_name            facility_type  country   capacity_mw  avg_efficiency_pct  overall_rank  rank_within_type  performance_quartile  percentile
-----------------------  -------------  --------  -----------  ------------------  ------------  ----------------  --------------------  ----------
SolarPlant_East_07       solar          Denmark        87.43               38.21             1                 1                     1       100.0
WindFarm_North_03        wind           Norway        412.50               37.84             2                 1                     1        94.7
SolarPlant_Central_12    solar          Sweden        203.11               36.90             3                 2                     1        89.5
WindFarm_South_01        wind           Finland       298.00               35.43             4                 2                     1        84.2
Substation_West_18       substation     Denmark        55.00               34.71             5                 1                     1        78.9
...
```

---

## Sample Output — Anomaly Detection (04) top-5

```
reading_id  sensor_id  recorded_at               value      z_score  facility_name          sensor_type   was_flagged_in_source
----------  ---------  ------------------------  ---------  -------  ---------------------  ------------  ---------------------
4821903     17         2023-07-14T13:35:00+00    1247.5000    18.43  WindFarm_North_03      power_output  true
1093421     5          2023-03-02T08:10:00+00    -62.0000     16.21  SolarPlant_East_07     temperature   true
6102847     42         2023-11-29T22:45:00+00     75.0000     15.87  Substation_West_18     wind_speed    true
2984510     23         2023-05-18T14:20:00+00    904.0000     14.92  WindFarm_South_01      power_output  true
5417623     38         2023-09-07T06:55:00+00   -64.5000     13.54  SolarPlant_Central_12  temperature   true
```

---

## Recommended Commit Sequence

```
git commit -m "Add project structure and environment config"
git commit -m "Add synthetic data generator for facilities, sensors, readings"
git commit -m "Add PostgreSQL schema with indexes"
git commit -m "Add Python ingestion pipeline with chunked loading and error handling"
git commit -m "Add data quality SQL checks and pytest validation tests"
git commit -m "Add rolling average analysis with 24h window function"
git commit -m "Add z-score anomaly detection using CTEs and monthly stats"
git commit -m "Add facility efficiency ranking with RANK, NTILE, PERCENT_RANK"
git commit -m "Add monthly report with MoM comparison and anomaly severity"
git commit -m "Add run_report.py pipeline, FastAPI endpoint, and complete README"
```

---

## What This Proves to a Hiring Manager

| JD Requirement | How It Is Covered |
|---|---|
| ETL pipeline experience | `ingest.py` with chunked loading, rollback on failure, idempotent inserts |
| Intermediate / advanced SQL | CTEs, window functions, ranking, time-series LAG, z-score anomaly detection |
| Relational database schema design | Normalised 3-table schema with FK constraints, named columns (no reserved-word clashes) |
| Data quality and validation | Quality-check SQL + 5-assertion pytest suite |
| Python for automation | `run_report.py` automated reporting pipeline |
| Docker / containerisation | PostgreSQL 15 via Docker Compose — one-command environment setup |
| API / data product mindset | FastAPI endpoint serving anomaly and ranking data as JSON |
| Git with meaningful commit history | 10-step commit sequence above |