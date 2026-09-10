# Sport Analytics — 2026 (WHOOP, Weather & Moon Phase)

Personal ETL/analytics pipeline that turns WHOOP fitness data, local weather, and moon-phase data into a daily operations dashboard: current form at a glance, plus history at day/week/month granularity.

## 🎯 Overview

Adapted from an earlier `sport_analytics` project that also ingested Strava. This version drops Strava, keeps WHOOP, and adds local weather (Open-Meteo) as a new source. It's also the first version of this project with real orchestration: Airflow runs the whole pipeline on a daily schedule instead of requiring manual CLI runs.

## 🏗️ Architecture

```
WHOOP API ─┐                                 ┌─→ source.duckdb (raw + staging views)
            ├─→ extract (raw JSON) ─→ load ──┤
Open-Meteo ─┘                                 └─→ dbt seed/run/test per layer
                                                     │
                                        transform.duckdb (intermediate tables)
                                                     │
                                        analytics.duckdb (fact/dim tables)
                                                     │
                                         FastAPI + static HTML dashboard
```

Orchestrated by Airflow (`3_orchestration/`, docker-compose, daily schedule): extract → load → `dbt run`/`dbt test` per layer, in the order the three-database dbt setup requires.

### Database architecture

Three separate DuckDB files, one per pipeline stage — not three schemas in one file:

- `0_data/database/source.duckdb` — raw WHOOP/weather tables + seed CSVs + staging views
- `0_data/database/transform.duckdb` — intermediate, per-source enriched tables
- `0_data/database/analytics.duckdb` — final fact/dim tables the dashboard reads from

dbt attaches the upstream database file(s) automatically per target via a macro — see `CLAUDE.md` for the mechanics and the resulting `--target` requirement.

## 📊 Data Sources

### WHOOP

Recovery, sleep, and workout data via the WHOOP API (OAuth). One-time browser-based auth (`1_elt/0_extract/whoop/auth_whoop.py`), then incremental daily extracts.

### Weather (Open-Meteo)

Daily temperature, precipitation, wind, and sunshine data for the configured location via the free, keyless Open-Meteo API. A one-time historical backfill (`archive` endpoint) plus a daily incremental pull (`forecast` endpoint with a lookback window, so late corrections to recent days are picked up). Modeled and tested in dbt, exposed via `/weather` on the API — not yet shown in the dashboard frontend (planned as a future panel).

### Moon phase

Static seed (`1_elt/2_transform/seeds/mooncalender.csv`, 2024-01-01 through 2026-12-31), joined onto WHOOP sleep data by date. Shown as an overlay in the dashboard's sleep panel (recovery/strain/workouts are not correlated against moon phase — that's WHOOP-only data with no obvious mechanism, so it's kept out of those panels to avoid implying a connection that isn't there).

## 🛠️ Tech Stack

- **Extraction**: Python, `requests`, WHOOP OAuth client
- **Storage**: DuckDB
- **Transformation**: dbt (`dbt-duckdb`)
- **Orchestration**: Apache Airflow (docker-compose, LocalExecutor)
- **API**: FastAPI
- **Dashboard**: static HTML + Chart.js (no build step)
- **Tooling**: `uv`, `pre-commit` (black, ruff, sqlfluff)

## 📁 Project Structure

```
.
├── 0_data/
│   ├── database/            # source.duckdb, transform.duckdb, analytics.duckdb (gitignored)
│   └── raw/{whoop,weather}/ # raw JSON dumps (gitignored)
├── 1_elt/
│   ├── 0_extract/{whoop,weather}/
│   ├── 1_load/{whoop,weather}/
│   └── 2_transform/         # dbt project
├── 2_analytics/
│   └── dashboard/           # FastAPI + static HTML operations dashboard
├── 3_orchestration/         # Airflow (docker-compose, DAG)
├── config_sample.yml        # copy to config.yml and fill in credentials
├── config_loader.py
└── CLAUDE.md                # architecture rationale, gotchas, dev commands
```

## 🚀 Getting Started

### Prerequisites

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker (only needed for Airflow orchestration, not for manual runs)
- A WHOOP account (for OAuth credentials)

### Installation

```bash
uv sync
uv run pre-commit install
```

### Configuration

```bash
cp config_sample.yml config.yml
```

Fill in your WHOOP `client_id`/`client_secret` in `config.yml`, then run the one-time OAuth flow:

```bash
python 1_elt/0_extract/whoop/auth_whoop.py
```

Weather needs no credentials — Open-Meteo is free and keyless. The `weather:` block in `config.yml` must be set to your location.

## 📖 Usage

See `CLAUDE.md` for the full command reference (extract, load, dbt per layer, dashboard, Airflow). Short version:

```bash
# Extract + load
python 1_elt/0_extract/whoop/extract_whoop_data.py
python 1_elt/1_load/whoop/load_whoop_data.py
python 1_elt/0_extract/weather/extract_weather_backfill.py --start-date 2025-01-01   # once
python 1_elt/0_extract/weather/extract_weather_data.py
python 1_elt/1_load/weather/load_weather_data.py

# Transform (from 1_elt/2_transform/, with DBT_PROFILES_DIR=.)
dbt seed --target source
dbt run --select 'staging.*' --target source
dbt run --select 'intermediate.*' --target transform
dbt run --select 'metrics.*' --target analytics

# Dashboard
uv run uvicorn "2_analytics.dashboard.api:app" --reload
cd 2_analytics/dashboard && python3 -m http.server 5500   # then open http://127.0.0.1:5500/

# Orchestration (optional — runs the whole pipeline daily)
cd 3_orchestration && docker compose up --build
```

## 🗄️ Database Schema

Key tables (in `analytics.duckdb`):

| Table | Description |
|---|---|
| `whoop.fct_whoop_recovery` | Daily recovery score, RHR, HRV |
| `whoop.fct_whoop_sleeps` | Sleep duration + stage breakdown, moon phase |
| `whoop.fct_whoop_sleep_quality` | Sleep performance/efficiency/debt, moon phase |
| `whoop.fct_whoop_workouts` | Per-workout strain, heart rate, zones |
| `weather.fct_weather_daily` | Daily local weather |
| `dates.dim_dates` | Date spine |
| `semantic.fct_daily_overview` | One row per day: WHOOP + moon + weather combined |
| `semantic.data_check` | Per-date data availability across sources |

## 🧪 Testing

```bash
# dbt tests, per layer with the matching target
cd 1_elt/2_transform
dbt test --select 'staging.*' --target source
dbt test --select 'intermediate.*' --target transform
dbt test --select 'metrics.*' --target analytics

# Dashboard JS unit tests
node 2_analytics/dashboard/test-dashboard-utils.js
```

## 📝 Code Quality

```bash
pre-commit run --all-files   # black + ruff (Python), sqlfluff lint/fix (SQL, duckdb dialect)
```

## 🔧 Development

### Adding a new data source

Follow the WHOOP/weather pattern: `1_elt/0_extract/<source>/` (client + extract-to-JSON script), `1_elt/1_load/<source>/` (JSON → `source.duckdb`, choose skip-existing vs upsert-by-date depending on whether the source's records are immutable), then `staging` → `intermediate` → `metrics` dbt models under the matching schema (add a branch to `macros/generate_schema_name.sql` if it's a new schema name).

### Adding to the dashboard

Add an endpoint to `2_analytics/dashboard/api.py`, then a render function in `index.html` using the existing `dashboard-utils.js` helpers (`computeKpiDeltas`, `groupByDay`/`groupByISOWeek`/`groupByMonth`) for consistent KPI tiles and granularity toggling.
