with

activity_mapping as (
    select * from {{ ref('stg_dbt_seeds_activity_mapping') }}
),

enhanced as (
    select distinct
        activity_id as whoop_workout_activity_name_id,
        aligned_activity_name as activity_name,
        is_sport_exercise

    from activity_mapping
)

select * from enhanced
