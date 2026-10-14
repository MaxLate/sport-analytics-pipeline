# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

End-to-end ELT pipeline that extracts WHOOP fitness data via its API and local weather data via the free Open-Meteo API, loads both into DuckDB, transforms them with dbt into a Kimball-style dimensional model (enriched with a static moon-phase seed), and serves the result through a FastAPI + static-HTML operations dashboard. Orchestrated with Airflow (docker-compose, LocalExecutor) for a daily run.

Adapted from an earlier personal project (`sport_analytics`) that additionally ingested Strava — Strava is not part of this project. The moon-phase seed and the WHOOP extract/load code are ported near-verbatim from that project; weather ingestion and the Airflow orchestration are new.

Personal portfolio project. CI in `.github/workflows/ci.yml` runs the whole pipeline on sample data (ruff, sqlfluff, `dbt build`, pytest, Airflow image + DAG import); `release.yml` publishes the Airflow image to GHCR on `v*` tags. Keep it green: no secrets or network beyond package installs are available in CI, so anything new must work on `load_sample_data.py` output.

## Commands

Python deps are managed with `uv` (Python >=3.12, venv at `.venv`).

```bash
uv sync                      # install deps
```

Config: copy `config_sample.yml` to `config.yml` (gitignored) and fill in WHOOP API credentials before running extract scripts. Weather needs no credentials (Open-Meteo is a free, keyless API) — only the `weather.latitude`/`longitude`/`timezone` block, which must be set to your location.

WHOOP auth is a one-time interactive step:

```bash
python 1_elt/0_extract/whoop/auth_whoop.py   # opens a browser OAuth flow, writes tokens into config.yml
```

### ELT pipeline (run in order, from repo root)

```bash
# 1. Extract — into 0_data/raw/ (incremental)
python 1_elt/0_extract/whoop/extract_whoop_data.py
python 1_elt/0_extract/weather/extract_weather_backfill.py --start-date 2025-01-01   # one-time, wide historical backfill
python 1_elt/0_extract/weather/extract_weather_data.py                              # daily incremental (past_days window)

# 2. Load — raw JSON into 0_data/database/warehouse.duckdb (schemas whoop, weather)
python 1_elt/1_load/whoop/load_whoop_data.py       # dedupes by id, skip-existing
python 1_elt/1_load/weather/load_weather_data.py   # upserts by date_day (recent days can be revised)
```

### dbt transform (run from `1_elt/2_transform/`)

dbt project/profile name is `sport_analytics`, one target (`dev`) pointing at `0_data/database/warehouse.duckdb`. `profiles.yml` lives next to `dbt_project.yml` (not in `~/.dbt`), so set `DBT_PROFILES_DIR=.` explicitly, especially in non-interactive contexts like Airflow:

```bash
cd 1_elt/2_transform
export DBT_PROFILES_DIR=.

dbt deps                                                    # dbt_utils (dbt_packages/ is gitignored)
dbt build                                                   # seeds, all models, all tests

# Layer by layer, as the Airflow DAG does it
dbt seed
dbt build --select staging --indirect-selection buildable
dbt build --select intermediate --indirect-selection buildable
dbt build --select marts --indirect-selection buildable

dbt docs generate && dbt docs serve
```

`--indirect-selection buildable` makes a test that spans two layers (the `relationships` test from `int_whoop_sleep` to `stg_dbt_seeds_moon_data`) run with its later layer, not before that layer's model exists.

### Code quality

```bash
pre-commit run --all-files   # black (Python) + ruff (Python lint) + sqlfluff lint/fix (SQL)
```

`.sqlfluff` is configured for the `duckdb` dialect (the actual DB engine — fixed from a `snowflake`/DuckDB mismatch in the project this was adapted from).

### Dashboard

```bash
uv run uvicorn "2_analytics.dashboard.api:app" --reload
cd 2_analytics/dashboard && python3 -m http.server 5500   # separate terminal, then open http://127.0.0.1:5500/
```

### Airflow orchestration

```bash
cd 3_orchestration
docker compose up --build   # first run also creates the admin/admin user
PIPELINE_MODE=sample docker compose up --build   # sample data into demo.duckdb, no WHOOP credentials needed
# Airflow UI at http://localhost:8080, trigger "sport_analytics_pipeline" manually or wait for its 06:00 Europe/Berlin schedule
```

## Architecture

### One warehouse, one schema per layer

Everything lives in a single DuckDB file, `0_data/database/warehouse.duckdb`:

- `whoop`, `weather` — raw tables, written by the load scripts (declared as dbt sources)
- `seeds` — CSV seeds (`+schema: seeds` in `dbt_project.yml`)
- `staging` — views
- `intermediate` — tables
- `marts` — fact/dim tables; the dashboard API and the chat read only from here

Model schema placement is driven by `macros/generate_schema_name.sql`: a model's schema is its top-level folder under `models/` (`node.fqn[1]`), so new models land in the right layer without config. The source subfolders (`whoop/`, `weather/`, `dates/`, `core/`) are for organisation only.

### DuckDB single-writer constraint

DuckDB allows exactly one writer connection to a given `.duckdb` file at a time. Within the Airflow DAG this is naturally fine (loads and dbt runs against the same file are already sequenced). It does matter for the dashboard API: `2_analytics/dashboard/api.py` opens a fresh `duckdb.connect(path, read_only=True)` per request rather than holding a long-lived connection, so it never contends with an Airflow write in progress — if you see a lock error from the API while a pipeline run is active, that's why; just retry.

### Model layers (Kimball-ish dimensional modeling)

- `models/staging/` — 1:1 cleaned views over raw source tables (`stg_whoop_sleep`, `stg_whoop_workouts`, `stg_whoop_recovery`, `stg_weather_daily`, plus `stg_dbt_seeds_*` for seed data)
- `models/intermediate/` — per-source enriched tables (`int_whoop_sleep`, `int_whoop_workouts`, `int_whoop_recovery`, `int_weather_daily`). `int_whoop_sleep` left-joins the moon-phase seed onto `date_day`; `int_whoop_recovery` joins WHOOP's `whoop_recoveries` source to `whoop_sleeps` purely to borrow `sleep_onset`/`nap` for the same day-shift `date_day` logic used by `int_whoop_sleep`, since recovery rows have no timestamp of their own.
- `models/marts/` — final fact/dim tables, split by source (`whoop/`, `weather/`), plus:
  - `marts/dates/dim_dates.sql` — date dimension, spine anchored to the earliest date across WHOOP sleep and weather data
  - `marts/core/` — cross-source unified layer: `fct_daily_overview` (one row per day: WHOOP recovery/sleep/workout aggregates + moon phase + weather, the table the dashboard's KPI/overview logic is built on) and `data_check` (per-date data availability across sources)

Seeds (`seeds/activity_mapping.csv`, `seeds/mooncalender.csv`) provide manual mapping/lookup data joined into intermediate models. `activity_mapping.csv` is filtered to WHOOP-only rows (the source project also had Strava rows). `mooncalender.csv` covers 2024-01-01 through 2026-12-31 as ported — it will need regenerating (e.g. via the `astral` package's `astral.moon.phase()`) before it runs out; not yet automated.

Weather data (`fct_weather_daily`) is modeled, tested, and wired into the dashboard's Weather panel.

Default materialization is `table`; staging is overridden to `view` (see `dbt_project.yml` `models:` block).

### Extract/Load scripts

Each source (`1_elt/0_extract/<source>/`, `1_elt/1_load/<source>/`) has an API client, an extract script that writes raw JSON to `0_data/raw/<source>/`, and a load script that writes into its raw schema in `warehouse.duckdb`. WHOOP's load is append-only (skip rows whose id already exists — WHOOP records are immutable once created). Weather's load instead **upserts by `date_day`** (delete existing rows for the incoming dates, then insert): Open-Meteo's `forecast` endpoint can revise the last few days as its model updates, so a fixed lookback window is intentionally re-fetched and overwritten on every run rather than skipped.

`config_loader.py` (repo root) is a shared `Config` wrapper around `config.yml`; it also supports writing back updated OAuth tokens via `Config.update(...)`.

### Airflow

`3_orchestration/dags/sport_analytics_pipeline.py` runs daily: extract WHOOP + weather in parallel, load each into `warehouse.duckdb`, then `dbt seed` and one `dbt build` per layer (staging → intermediate → marts). Tests are part of `dbt build` and blocking: a failing test stops the downstream layers. With `PIPELINE_MODE=sample` (docker-compose env), extract + load are replaced by `1_elt/1_load/sample/load_sample_data.py` and every task gets `WAREHOUSE_PATH=.../demo.duckdb`.

dbt packages are installed into the image at build time (`DBT_PACKAGES_INSTALL_PATH=/opt/airflow/dbt_packages`, read by `packages-install-path` in `dbt_project.yml`), not into the bind-mounted `dbt_packages/`: `dbt deps` through the macOS bind mount left half-extracted packages (missing `dbt_project.yml`) that also broke local runs. After changing `packages.yml`, rebuild the image. The image's dbt/DuckDB versions are pinned in `requirements-airflow.txt` to match `uv.lock`. Tasks shell out via `BashOperator` (`python3 ...` / `dbt ...`) rather than `PythonOperator`, so a manual run from a terminal and an Airflow-triggered run execute the exact same commands. The whole repo is bind-mounted read-write into the Airflow containers at `/opt/airflow/project`, which is also how `config.yml` reaches the containers — no separate secrets mechanism for this single-user local setup.
