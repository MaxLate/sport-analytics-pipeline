with

whoop_recovery_data as (
    select * from {{ ref('stg_whoop_recovery') }}
),

enhanced as (
    select

        row_number() over (order by sleep_onset) as whoop_recovery_id,

        -- date day
        -- mirrors int_whoop_sleep.sql: sleep onset after midnight but before noon belongs to the previous night
        case
            when extract(hour from sleep_onset) < 12 and nap is false then (sleep_onset :: date - interval '1 day') :: date
            else sleep_onset :: date
        end as date_day,

        recovery_score,
        resting_heart_rate,
        hrv_rmssd_milli,
        spo2_percentage,
        skin_temp_celsius

    from whoop_recovery_data
)

select * from enhanced
