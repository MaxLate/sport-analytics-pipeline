with

whoop_sleep_data as (
    select * from {{ ref('stg_whoop_sleep') }}
),

moon_data as (
    select * from {{ ref('stg_dbt_seeds_moon_data') }}
),

enhanced as (

    select

        -- sleep id
        row_number() over (order by sleep_onset) as sleep_id,
        row_number() over (partition by date_trunc('day', sleep_onset) order by sleep_onset) as sleep_id_of_day,

        -- date day
        -- it can happen that the sleep onset start after 00:00, so we need to subtract 1 day for the night date
        case
            when extract(hour from sleep_onset) < 12 and nap is false then (sleep_onset :: date - interval '1 day') :: date
            else sleep_onset :: date
        end as date_day,

        date_trunc('day', sleep_onset) :: date as sleep_start_date,
        sleep_onset,

        date_trunc('day', wake_onset) :: date as wake_up_date,
        wake_onset,


        -- sleep duration: sum of sleep stages, converted from milliseconds to minutes
        (
            light_sleep_time_milli + slow_wave_sleep_time_milli + rem_sleep_time_milli
        ) / 60000.0 :: decimal(10, 2) as asleep_duration_minutes,
        asleep_duration_minutes / 60 as asleep_duration_hours,

        in_bed_time_milli / 60000.0 :: decimal(10, 2) as in_bed_duration_minutes,
        in_bed_duration_minutes / 60 as in_bed_duration_hours,

        light_sleep_time_milli / 60000.0 :: decimal(10, 2) as light_sleep_duration_minutes,
        light_sleep_duration_minutes / 60 as light_sleep_duration_hours,

        slow_wave_sleep_time_milli / 60000.0 :: decimal(10, 2) as deep_sleep_duration_minutes,
        deep_sleep_duration_minutes / 60 as deep_sleep_duration_hours,

        rem_sleep_time_milli / 60000.0 :: decimal(10, 2) as rem_duration_minutes,
        rem_duration_minutes / 60 as rem_duration_hours,

        awake_time_milli / 60000.0 :: decimal(10, 2) as awake_duration_minutes,
        awake_duration_minutes / 60 as awake_duration_hours,

        -- sleep quality
        sleep_performance,
        respiratory_rate,

        -- sleep need: baseline + sleep debt + recent strain + recent nap, converted to minutes
        -- (WHOOP reports the nap component as a non-positive reduction)
        (
            sleep_need_baseline_milli
            + sleep_need_from_sleep_debt_milli
            + sleep_need_from_recent_strain_milli
            + sleep_need_from_recent_nap_milli
        ) / 60000.0 :: decimal(10, 2) as sleep_need_minutes,
        sleep_need_minutes / 60 as sleep_need_hours,

        sleep_need_from_sleep_debt_milli / 60000.0 :: decimal(10, 2) as sleep_debt_minutes,
        sleep_debt_minutes / 60 as sleep_debt_hours,

        sleep_efficiency,
        sleep_consistency,
        nap

    from whoop_sleep_data
),

combined_data as (

    select
        enhanced.*,

        moon_data.moon_phase,
        moon_data.illumination as moon_illumination,
        moon_data.phase_cycle as moon_phase_cycle

    from enhanced
    left join moon_data on enhanced.date_day = moon_data.date_day
)

select * from combined_data
