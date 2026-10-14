"""
Daily pipeline: extract WHOOP + weather -> load into warehouse.duckdb -> dbt
build the staging, intermediate and marts layers in order.

PIPELINE_MODE=sample (set in docker-compose) swaps extract + load for the
synthetic sample loader and writes to demo.duckdb instead, so the pipeline
runs without WHOOP credentials or network access.

Runs as plain Python/dbt CLI invocations via BashOperator rather than
PythonOperator, since the extract/load scripts already work standalone from
the project root and dbt is driven from its own CLI everywhere else in this
project (see 1_elt/2_transform/HOW_TO_RUN.md) — reusing that exact invocation
here keeps manual runs and Airflow runs identical.
"""

import os

import pendulum
from airflow.models.dag import DAG
from airflow.operators.bash import BashOperator
from airflow.utils.task_group import TaskGroup

PROJECT_DIR = "/opt/airflow/project"
TRANSFORM_DIR = f"{PROJECT_DIR}/1_elt/2_transform"
DATABASE_DIR = f"{PROJECT_DIR}/0_data/database"

PIPELINE_MODE = os.environ.get("PIPELINE_MODE", "live")
if PIPELINE_MODE not in {"live", "sample"}:
    raise ValueError(f"PIPELINE_MODE must be 'live' or 'sample', got {PIPELINE_MODE!r}")
WAREHOUSE_PATH = (
    f"{DATABASE_DIR}/{'demo' if PIPELINE_MODE == 'sample' else 'warehouse'}.duckdb"
)

# profiles.yml lives next to dbt_project.yml, not in ~/.dbt — pass it explicitly.
# Via env var rather than a `--profiles-dir` CLI flag: dbt 1.12 moved that flag
# from global to per-subcommand, which broke `dbt --profiles-dir . <cmd>`.
DBT_BASE = f"cd {TRANSFORM_DIR} && DBT_PROFILES_DIR=. dbt"
DBT_LAYERS = ["staging", "intermediate", "marts"]

default_args = {
    "owner": "sport-analytics",
    "retries": 0,
    "env": {"WAREHOUSE_PATH": WAREHOUSE_PATH},
    "append_env": True,
}

with DAG(
    dag_id="sport_analytics_pipeline",
    description="Extract WHOOP + weather, load into DuckDB, dbt build staging -> intermediate -> marts.",
    default_args=default_args,
    schedule="0 6 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="Europe/Berlin"),
    catchup=False,
    max_active_runs=1,
    tags=["sport-analytics", PIPELINE_MODE],
) as dag:

    if PIPELINE_MODE == "sample":
        # --force: the sample data is deterministic, so reloading it is idempotent.
        ingest = BashOperator(
            task_id="load_sample_data",
            bash_command=f"cd {PROJECT_DIR} && python3 1_elt/1_load/sample/load_sample_data.py --force",
        )
    else:
        with TaskGroup(group_id="extract"):
            extract_whoop = BashOperator(
                task_id="extract_whoop",
                bash_command=f"cd {PROJECT_DIR} && python3 1_elt/0_extract/whoop/extract_whoop_data.py",
                retries=2,
                retry_delay=pendulum.duration(minutes=5),
            )
            extract_weather = BashOperator(
                task_id="extract_weather",
                bash_command=f"cd {PROJECT_DIR} && python3 1_elt/0_extract/weather/extract_weather_data.py",
                retries=2,
                retry_delay=pendulum.duration(minutes=5),
            )

        with TaskGroup(group_id="load") as ingest:
            load_whoop = BashOperator(
                task_id="load_whoop",
                bash_command=f"cd {PROJECT_DIR} && python3 1_elt/1_load/whoop/load_whoop_data.py",
            )
            load_weather = BashOperator(
                task_id="load_weather",
                bash_command=f"cd {PROJECT_DIR} && python3 1_elt/1_load/weather/load_weather_data.py",
            )

        extract_whoop >> load_whoop
        extract_weather >> load_weather

    # dbt packages are installed in the image (see Dockerfile), so no dbt deps task.
    dbt_seed = BashOperator(
        task_id="dbt_seed",
        bash_command=f"{DBT_BASE} seed",
    )

    ingest >> dbt_seed
    previous = dbt_seed
    for layer in DBT_LAYERS:
        # buildable: a test runs in the layer of its last parent, so the
        # relationships test int_whoop_sleep -> stg_dbt_seeds_moon_data runs
        # with intermediate instead of failing in staging on a fresh warehouse.
        dbt_build = BashOperator(
            task_id=f"dbt_build_{layer}",
            bash_command=f"{DBT_BASE} build --select {layer} --indirect-selection buildable",
        )
        previous >> dbt_build
        previous = dbt_build
