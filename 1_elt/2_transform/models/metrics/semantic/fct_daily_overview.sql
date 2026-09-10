with

dates as (
    select * from {{ ref('dim_dates') }}
),

recovery as (
    select * from {{ ref('fct_whoop_recovery') }}
),

sleep_quality as (
    select * from {{ ref('fct_whoop_sleep_quality') }}
    where nap is false
),

workouts as (
    select
        date_day,
        count(*) as workout_count,
        sum(activity_strain) as total_strain,
        max(activity_strain) as max_strain
    from {{ ref('fct_whoop_workouts') }}
    group by date_day
),

weather as (
    select * from {{ ref('fct_weather_daily') }}
),

final as (

    select

        dates.date_day,
        dates.day_name,
        dates.is_weekend,

        recovery.recovery_score,
        recovery.resting_heart_rate,
        recovery.hrv_rmssd_milli,

        sleep_quality.sleep_performance,
        sleep_quality.sleep_efficiency,
        sleep_quality.moon_phase,
        sleep_quality.moon_phase_cycle,
        sleep_quality.moon_illumination,

        workouts.workout_count,
        workouts.total_strain,
        workouts.max_strain,

        weather.temperature_mean_celsius,
        weather.precipitation_sum_mm

    from dates
    left join recovery on dates.date_day = recovery.date_day
    left join sleep_quality on dates.date_day = sleep_quality.date_day
    left join workouts on dates.date_day = workouts.date_day
    left join weather on dates.date_day = weather.date_day
    where dates.date_day <= current_date
)

select * from final
