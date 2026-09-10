"""
Daily pipeline: extract WHOOP + weather -> load into source.duckdb -> run the
dbt layers in the order the multi-database setup requires (source ->
transform -> analytics, each with its own --target).

Runs as plain Python/dbt CLI invocations via BashOperator rather than
PythonOperator, since the extract/load scripts already work standalone from
the project root and dbt is driven from its own CLI everywhere else in this
project (see 1_elt/2_transform/HOW_TO_RUN.md) — reusing that exact invocation
here keeps manual runs and Airflow runs identical.
"""

import pendulum
from airflow.models.dag import DAG
from airflow.operators.bash import BashOperator
from airflow.utils.task_group import TaskGroup

PROJECT_DIR = "/opt/airflow/project"
TRANSFORM_DIR = f"{PROJECT_DIR}/1_elt/2_transform"

# profiles.yml lives next to dbt_project.yml, not in ~/.dbt — pass it explicitly.
DBT_BASE = f"cd {TRANSFORM_DIR} && dbt --profiles-dir ."

default_args = {
    "owner": "sport-analytics",
    "retries": 0,
}

with DAG(
    dag_id="sport_analytics_pipeline",
    description="Extract WHOOP + weather, load into DuckDB, run dbt (source -> transform -> analytics).",
    default_args=default_args,
    schedule="0 6 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="Europe/Berlin"),
    catchup=False,
    max_active_runs=1,
    tags=["sport-analytics"],
) as dag:

    with TaskGroup(group_id="extract") as extract_group:
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

    with TaskGroup(group_id="load") as load_group:
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

    dbt_seed = BashOperator(
        task_id="dbt_seed",
        bash_command=f"{DBT_BASE} seed --target source",
    )

    dbt_staging = BashOperator(
        task_id="dbt_run_staging",
        bash_command=f"{DBT_BASE} run --select 'staging.*' --target source",
    )
    dbt_test_staging = BashOperator(
        task_id="dbt_test_staging",
        bash_command=f"{DBT_BASE} test --select 'staging.*' --target source",
    )

    dbt_intermediate = BashOperator(
        task_id="dbt_run_intermediate",
        bash_command=f"{DBT_BASE} run --select 'intermediate.*' --target transform",
    )
    dbt_test_intermediate = BashOperator(
        task_id="dbt_test_intermediate",
        bash_command=f"{DBT_BASE} test --select 'intermediate.*' --target transform",
    )

    dbt_metrics = BashOperator(
        task_id="dbt_run_metrics",
        bash_command=f"{DBT_BASE} run --select 'metrics.*' --target analytics",
    )
    dbt_test_metrics = BashOperator(
        task_id="dbt_test_metrics",
        bash_command=f"{DBT_BASE} test --select 'metrics.*' --target analytics",
    )

    load_group >> dbt_seed >> dbt_staging >> dbt_test_staging
    dbt_test_staging >> dbt_intermediate >> dbt_test_intermediate
    dbt_test_intermediate >> dbt_metrics >> dbt_test_metrics
