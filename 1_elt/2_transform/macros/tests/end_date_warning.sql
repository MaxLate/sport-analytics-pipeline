{% test end_date_warning(model, column_name="date_day", warn_days=30) %}

-- Warns when today is within warn_days of the model's latest date (inclusive of the last day).
with params as (
    select max({{ column_name }})::date as end_date
    from {{ model }}
)

select 1
from params
where current_date >= end_date - {{ warn_days }}
  and current_date <= end_date

{% endtest %}
