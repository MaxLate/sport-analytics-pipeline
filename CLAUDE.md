# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

End-to-end ELT pipeline that extracts WHOOP fitness data via its API and local weather data via the free Open-Meteo API, loads both into DuckDB, transforms them with dbt into a Kimball-style dimensional model (enriched with a static moon-phase seed), and serves the result through a FastAPI + static-HTML operations dashboard. Orchestrated with Airflow (docker-compose, LocalExecutor) for a daily run.

Adapted from an earlier personal project (`sport_analytics`) that additionally ingested Strava — Strava is not part of this project. The moon-phase seed and the WHOOP extract/load code are ported near-verbatim from that project; weather ingestion and the Airflow orchestration are new.

Personal project — WIP, no CI.

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

# 2. Load — raw JSON into 0_data/database/source.duckdb
python 1_elt/1_load/whoop/load_whoop_data.py       # dedupes by id, skip-existing
python 1_elt/1_load/weather/load_weather_data.py   # upserts by date_day (recent days can be revised)
```

### dbt transform (run from `1_elt/2_transform/`)

dbt project/profile name is `sport_analytics`, three targets mapping to three separate DuckDB files — you must pick the right `--target` per layer, dbt does not do this automatically. `profiles.yml` lives next to `dbt_project.yml` (not in `~/.dbt`), so pass `--profiles-dir .` (or set `DBT_PROFILES_DIR=.`) explicitly, especially in non-interactive contexts like Airflow:

```bash
cd 1_elt/2_transform
export DBT_PROFILES_DIR=.

dbt seed --target source                                    # load CSV seeds (moon phase, activity mapping)

dbt run --select 'staging.*' --target source                # views, in source.duckdb
dbt run --select 'intermediate.*' --target transform        # tables, in transform.duckdb
dbt run --select 'metrics.*' --target analytics             # tables, in analytics.duckdb

dbt test --select 'staging.*' --target source
dbt test --select 'intermediate.*' --target transform
dbt test --select 'metrics.*' --target analytics

dbt docs generate && dbt docs serve
```

Running `dbt test` (or any cross-layer selection) without a target, or a test that spans two layers (e.g. a `relationships` test from an intermediate model to a staging model) run against the wrong `--target`, fails with `Catalog "transform" does not exist` or similar — always test each layer with its own target, same as `dbt run`.

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
docker compose up --build   # first run also creates the airflow/airflow admin user
# Airflow UI at http://localhost:8080, trigger "sport_analytics_pipeline" manually or wait for its 06:00 Europe/Berlin schedule
```

## Architecture

### Three-database dbt design (the key thing to understand)

dbt materializes each pipeline layer into a **separate DuckDB file**, not separate schemas in one database:

- `source.duckdb` — raw source tables + staging views (target `source`)
- `transform.duckdb` — intermediate tables (target `transform`)
- `analytics.duckdb` — metrics/fact/dim tables (target `analytics`)

Cross-database refs work because `on-run-start` in `dbt_project.yml` runs the `attach_databases()` macro (`macros/attach_databases.sql`), which `ATTACH`es the upstream database file(s) under the target currently being built (e.g. building `transform` attaches `source`; building `analytics` attaches both `source` and `transform`). Paths inside the macro are relative to the dbt project dir (`1_elt/2_transform/`) and hardcoded — if the project moves, fix them there.

Schema (not database) placement inside each file is driven by `macros/generate_schema_name.sql`: it inspects the model name/path and buckets into `whoop`, `weather`, `seeds`, `dates`, or `semantic` schemas automatically — new models get schema'd by naming convention, not by explicit config.

### DuckDB single-writer constraint

DuckDB allows exactly one writer connection to a given `.duckdb` file at a time. Within the Airflow DAG this is naturally fine (loads and dbt runs against the same file are already sequenced). It does matter for the dashboard API: `2_analytics/dashboard/api.py` opens a fresh `duckdb.connect(path, read_only=True)` per request rather than holding a long-lived connection, so it never contends with an Airflow write in progress — if you see a lock error from the API while a pipeline run is active, that's why; just retry.

### Model layers (Kimball-ish dimensional modeling)

- `models/staging/` — 1:1 cleaned views over raw source tables (`stg_whoop_sleep`, `stg_whoop_workouts`, `stg_whoop_recovery`, `stg_weather_daily`, plus `stg_dbt_seeds_*` for seed data)
- `models/intermediate/` — per-source enriched tables (`int_whoop_sleep`, `int_whoop_workouts`, `int_whoop_recovery`, `int_weather_daily`). `int_whoop_sleep` left-joins the moon-phase seed onto `date_day`; `int_whoop_recovery` joins WHOOP's `whoop_recoveries` source to `whoop_sleeps` purely to borrow `sleep_onset`/`nap` for the same day-shift `date_day` logic used by `int_whoop_sleep`, since recovery rows have no timestamp of their own.
- `models/metrics/` — final fact/dim tables, split by source (`whoop/`, `weather/`), plus:
  - `metrics/dates/dim_dates.sql` — date dimension, spine anchored to the earliest date across WHOOP sleep and weather data
  - `metrics/semantic/` — cross-source unified layer: `fct_daily_overview` (one row per day: WHOOP recovery/sleep/workout aggregates + moon phase + weather, the table the dashboard's KPI/overview logic is built on) and `data_check` (per-date data availability across sources)

Seeds (`seeds/activity_mapping.csv`, `seeds/mooncalender.csv`) provide manual mapping/lookup data joined into intermediate models. `activity_mapping.csv` is filtered to WHOOP-only rows (the source project also had Strava rows). `mooncalender.csv` covers 2024-01-01 through 2026-12-31 as ported — it will need regenerating (e.g. via the `astral` package's `astral.moon.phase()`) before it runs out; not yet automated.

Weather data (`fct_weather_daily`) is modeled and tested but **not yet wired into the dashboard frontend** — it's a deliberate follow-up, not a bug.

Default materialization is `table`; staging is overridden to `view` (see `dbt_project.yml` `models:` block).

### Extract/Load scripts

Each source (`1_elt/0_extract/<source>/`, `1_elt/1_load/<source>/`) has an API client, an extract script that writes raw JSON to `0_data/raw/<source>/`, and a load script that writes into `source.duckdb`. WHOOP's load is append-only (skip rows whose id already exists — WHOOP records are immutable once created). Weather's load instead **upserts by `date_day`** (delete existing rows for the incoming dates, then insert): Open-Meteo's `forecast` endpoint can revise the last few days as its model updates, so a fixed lookback window is intentionally re-fetched and overwritten on every run rather than skipped.

`config_loader.py` (repo root) is a shared `Config` wrapper around `config.yml`; it also supports writing back updated OAuth tokens via `Config.update(...)`.

### Airflow

`3_orchestration/dags/sport_analytics_pipeline.py` runs daily: extract WHOOP + weather in parallel, load each into `source.duckdb`, then the three dbt layers in strict sequence (each `dbt run` immediately followed by its matching `dbt test`, same `--target` both times). Tasks shell out via `BashOperator` (`python3 ...` / `dbt ...`) rather than `PythonOperator`, so a manual run from a terminal and an Airflow-triggered run execute the exact same commands. The whole repo is bind-mounted read-write into the Airflow containers at `/opt/airflow/project`, which is also how `config.yml` reaches the containers — no separate secrets mechanism for this single-user local setup.
