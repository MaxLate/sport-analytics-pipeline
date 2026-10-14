"""Fail if a DAG does not import. Runs inside the Airflow image (CI), no metadata DB needed."""

import os
import sys

from airflow.models import DagBag

bag = DagBag(os.environ.get("DAGS_FOLDER", "/opt/airflow/dags"), include_examples=False)
if bag.import_errors:
    for path, error in bag.import_errors.items():
        print(f"{path}:\n{error}", file=sys.stderr)
    sys.exit(1)

mode = os.environ.get("PIPELINE_MODE", "live")
for dag_id, dag in sorted(bag.dags.items()):
    print(f"[{mode}] {dag_id}: {', '.join(sorted(task.task_id for task in dag.tasks))}")
