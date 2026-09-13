with

whoop_recovery_data as (
    select * from {{ ref('stg_whoop_recovery') }}
),

whoop_sleep_data as (
    select * from {{ ref('stg_whoop_sleep') }}
),

enhanced as (
    select

        row_number() over (order by whoop_sleep_data.sleep_onset) as whoop_recovery_id,

        -- date day
        -- mirrors int_whoop_sleep.sql: sleep onset after midnight but before noon belongs to the previous night
        case
            when extract(hour from whoop_sleep_data.sleep_onset) < 12 and whoop_sleep_data.nap is false then (whoop_sleep_data.sleep_onset :: date - interval '1 day') :: date
            else whoop_sleep_data.sleep_onset :: date
        end as date_day,

        whoop_recovery_data.score.recovery_score,
        whoop_recovery_data.score.resting_heart_rate,
        whoop_recovery_data.score.hrv_rmssd_milli,
        whoop_recovery_data.score.spo2_percentage,
        whoop_recovery_data.score.skin_temp_celsius

    from whoop_recovery_data
    left join whoop_sleep_data on whoop_recovery_data.whoop_sleep_uuid = whoop_sleep_data.sleep_id
)

select * from enhanced
