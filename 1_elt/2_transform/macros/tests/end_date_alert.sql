{% test end_date_alert(model, column_name="date_day") %}

-- Fails when the model's latest date is already in the past (today is no longer covered).
with params as (
    select max({{ column_name }})::date as end_date
    from {{ model }}
)

select 1
from params
where current_date > end_date

{% endtest %}
