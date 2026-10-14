FROM apache/airflow:2.10.5-python3.12

COPY requirements-airflow.txt /requirements-airflow.txt
RUN pip install --no-cache-dir -r /requirements-airflow.txt

# dbt packages live in the image, not in the bind-mounted project: writing
# them through the macOS bind mount left half-extracted packages behind.
ENV DBT_PACKAGES_INSTALL_PATH=/opt/airflow/dbt_packages
COPY --chown=airflow:root --from=dbt_project packages.yml package-lock.yml /opt/airflow/dbt_deps/
RUN cd /opt/airflow/dbt_deps \
    && printf "name: deps\nversion: '1.0'\nprofile: deps\npackages-install-path: %s\n" "$DBT_PACKAGES_INSTALL_PATH" > dbt_project.yml \
    && dbt deps \
    && test -f "$DBT_PACKAGES_INSTALL_PATH/dbt_utils/dbt_project.yml"
