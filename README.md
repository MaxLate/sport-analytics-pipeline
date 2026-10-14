# Sport Analytics — 2026 (WHOOP, Weather & Moon Phase)

Personal ETL/analytics pipeline that turns WHOOP fitness data, local weather, and moon-phase data into a daily operations dashboard: current form at a glance, plus history at day/week/month granularity.

## 🎯 Overview

Adapted from an earlier `sport_analytics` project that also ingested Strava. This version drops Strava, keeps WHOOP, and adds local weather (Open-Meteo) as a new source. It's also the first version of this project with real orchestration: Airflow runs the whole pipeline on a daily schedule instead of requiring manual CLI runs.

## 🏗️ Architecture

```
WHOOP API ─┐                                  warehouse.duckdb
            ├─→ extract (raw JSON) ─→ load ──→  whoop / weather   (raw)
Open-Meteo ─┘                                   seeds             (dbt seed)
                                                staging           (views)
                                                intermediate      (tables)
                                                marts             (fact/dim tables)
                                                     │
                                         FastAPI + static HTML dashboard
```

Orchestrated by Airflow (`3_orchestration/`, docker-compose, daily schedule): extract → load → `dbt seed` → `dbt build` per layer (staging → intermediate → marts). Tests are part of `dbt build`, so a failing test stops the downstream layers. dbt and DuckDB are pinned to the same versions as `uv.lock`, and dbt packages are installed into the image at build time.

### Database architecture

One DuckDB file, `0_data/database/warehouse.duckdb`, with one schema per layer:

- `whoop`, `weather` — raw tables written by the load scripts
- `seeds` — CSV seeds (moon phase, activity mapping)
- `staging` — 1:1 cleaned views over raw tables and seeds
- `intermediate` — per-source enriched tables
- `marts` — final fact/dim tables the dashboard and chat read from

The schema is the top-level model folder (`macros/generate_schema_name.sql`), so a new model lands in the right layer without extra config.

## 📊 Data Sources

### WHOOP

Recovery, sleep, and workout data via the WHOOP API (OAuth). One-time browser-based auth (`1_elt/0_extract/whoop/auth_whoop.py`), then incremental daily extracts.

### Weather (Open-Meteo)

Daily temperature, precipitation, wind, and sunshine data for the configured location via the free, keyless Open-Meteo API. A one-time historical backfill (`archive` endpoint) plus a daily incremental pull (`forecast` endpoint with a lookback window, so late corrections to recent days are picked up). Modeled and tested in dbt and exposed via `/weather` on the API. The dashboard uses it on the Sleep page, where each night's sleep performance is set against the wake-up day's minimum temperature.

### Moon phase

Static seed (`1_elt/2_transform/seeds/mooncalender.csv`, 2024-01-01 through 2026-12-31), joined onto WHOOP sleep data by date. The dashboard's Sleep page plots sleep performance against moon illumination and phase, and labels the result only as a Pearson association with its night count; it never claims cause. Recovery, strain and workouts are not set against moon phase at all.

## 🛠️ Tech Stack

- **Extraction**: Python, `requests`, WHOOP OAuth client
- **Storage**: DuckDB
- **Transformation**: dbt (`dbt-duckdb`)
- **Orchestration**: Apache Airflow (docker-compose, LocalExecutor)
- **API**: FastAPI
- **Dashboard**: static HTML + Chart.js (no build step)
- **Chat**: YAML semantic layer, `sqlglot` SQL guard, Google ADK agents on a local Ollama model
- **Tooling**: `uv`, `pre-commit` (black, ruff, sqlfluff)

## 📁 Project Structure

```
.
├── 0_data/
│   ├── database/            # warehouse.duckdb (gitignored)
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

### Quick start with sample data (no WHOOP account needed)

`load_sample_data.py` writes six months of deterministic synthetic WHOOP and weather data into the raw schemas, with the same column types as the real loads. It refuses to overwrite a warehouse that already holds raw data.

```bash
uv run python 1_elt/1_load/sample/load_sample_data.py
cd 1_elt/2_transform && export DBT_PROFILES_DIR=. && uv run dbt deps && uv run dbt build
```

To keep real and demo data apart, point everything at another file with `WAREHOUSE_PATH` (absolute path; read by dbt, the API and the chat):

```bash
export WAREHOUSE_PATH=$PWD/0_data/database/demo.duckdb
uv run python 1_elt/1_load/sample/load_sample_data.py --db-path "$WAREHOUSE_PATH"
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
dbt deps
dbt build        # seeds, models and tests for all layers

# Dashboard
uv run uvicorn "2_analytics.dashboard.api:app" --reload
cd 2_analytics/dashboard && python3 -m http.server 5500   # then open http://127.0.0.1:5500/

# Orchestration (optional — runs the whole pipeline daily)
cd 3_orchestration && docker compose up --build
# Without WHOOP credentials: the DAG loads sample data into demo.duckdb instead
cd 3_orchestration && PIPELINE_MODE=sample docker compose up --build
```

## 🗄️ Database Schema

Key tables (in `warehouse.duckdb`):

| Table | Description |
|---|---|
| `marts.fct_whoop_recovery` | Daily recovery score, RHR, HRV |
| `marts.fct_whoop_sleeps` | Sleep duration + stage breakdown, moon phase |
| `marts.fct_whoop_sleep_quality` | Sleep performance/efficiency/debt, moon phase |
| `marts.fct_whoop_workouts` | Per-workout strain, heart rate, zones |
| `marts.fct_weather_daily` | Daily local weather |
| `marts.dim_dates` | Date spine |
| `marts.fct_daily_overview` | One row per day: WHOOP + moon + weather combined |
| `marts.data_check` | Per-date data availability across sources |

## 💬 Ask your data (LLM module)

The dashboard has a chat panel (`POST /chat`) that answers questions from the marts. It is built around a small semantic layer, `2_analytics/dashboard/semantic_layer.yml`, written in the shape of dbt semantic models: each mart declares its grain, columns, entities (join keys) and measures. It is a hand-written YAML read by Python, not dbt's MetricFlow.

A question goes through two paths:

1. **Metric questions are compiled deterministically, no LLM.** "How many runs did I do in March 2026?" or "average recovery score in May 2026" match a declared measure or filter, are compiled to one SQL aggregate, and are answered with a fixed sentence ("You have done 8 runs in March 2026."). Same question, same SQL, same answer.
2. **Open questions go to a three-agent pipeline** (Google ADK, local Ollama model via LiteLLM): a scope agent checks relevance and looks up tables and allowed joins in the semantic layer, a SQL agent writes one query, an answer agent phrases the result from the returned rows only.

Guardrails:

- Every query, generated or compiled, is parsed with `sqlglot` and must be a single read-only `SELECT` on the tables declared in the semantic layer; file-reading functions are blocked. DuckDB is opened read-only.
- The executed SQL is shown under every answer.
- Contract tests (`test_semantic_contract.py`) fail when the YAML references a column the marts don't have, or an activity the dbt seed doesn't know.
- Ollama is optional: without it, metric questions still work and open questions return HTTP 503.

## 🧪 Testing

```bash
# dbt tests (from 1_elt/2_transform/, with DBT_PROFILES_DIR=.)
dbt test

# Dashboard and chat (API, SQL guard, query tool, semantic layer)
uv run pytest 2_analytics/dashboard

# Dashboard JS unit tests
node 2_analytics/dashboard/test-dashboard-utils.js
```

## 🔁 CI/CD (GitHub Actions)

- **`.github/workflows/ci.yml`**, on every pull request and push to `main`:
  - `pipeline` job: `uv sync --locked`, ruff, sqlfluff, load sample data, `dbt build` (all models and tests), pytest (including the semantic layer contract against the freshly built marts), dashboard JS tests. No secrets needed.
  - `airflow-image` job: builds the Airflow image (pinned dbt/DuckDB, dbt packages baked in) and imports the DAG in live and sample mode.
- **`.github/workflows/release.yml`**, on a `v*` tag: pushes the Airflow image to `ghcr.io/<owner>/sport-analytics-airflow` (tags `1.2.3`, `1.2`, `latest`) and creates a GitHub release with generated notes.

```bash
git tag v0.1.0 && git push origin v0.1.0   # cut a release
```

## 📝 Code Quality

```bash
pre-commit run --all-files   # black + ruff (Python), sqlfluff lint/fix (SQL, duckdb dialect)
```

## 🔧 Development

### Adding a new data source

Follow the WHOOP/weather pattern: `1_elt/0_extract/<source>/` (client + extract-to-JSON script), `1_elt/1_load/<source>/` (JSON → a raw `<source>` schema in `warehouse.duckdb`, choose skip-existing vs upsert-by-date depending on whether the source's records are immutable), then `staging` → `intermediate` → `marts` dbt models in a `<source>/` subfolder of each layer.

### Adding to the dashboard

The dashboard has three pages that share `dashboard.css` and `dashboard-page.js` (API base, colours, load errors, period toggle):

- `index.html` (Overview): four KPI tiles, Recovery and the chat panel
- `sleep.html`: main sleeps only (naps excluded), with moon and temperature associations for 30 days, 90 days, 1 year or all time
- `training.html`: training hours by activity, heart rate and strain per sport, and recent sessions; non-sport activities such as commuting are hidden unless "Include all activities" is ticked

Data logic lives in `dashboard-utils.js` as pure functions with `node:test` coverage (`filterByPeriod`, `pearsonCorrelation`, `stackTrainingHours`, `computeKpiDeltas` and others). Add an endpoint to `2_analytics/dashboard/api.py`, put the calculation in `dashboard-utils.js` with a test, and keep the page script to rendering.
