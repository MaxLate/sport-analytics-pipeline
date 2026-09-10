with

whoop_recovery_data as (
    select * from {{ source('whoop', 'whoop_recoveries') }}
),

whoop_sleep_data as (
    select * from {{ source('whoop', 'whoop_sleeps') }}
),

final as (
    select

        whoop_recovery_data.cycle_id :: bigint as whoop_cycle_id,
        whoop_recovery_data.sleep_id :: varchar as whoop_sleep_uuid,
        whoop_sleep_data.start :: timestamp as sleep_onset,
        whoop_sleep_data.nap :: boolean as nap,
        whoop_recovery_data.created_at :: timestamp as recovery_created_at,

        whoop_recovery_data.score.recovery_score :: decimal(10, 2) as recovery_score,
        whoop_recovery_data.score.resting_heart_rate :: decimal(10, 2) as resting_heart_rate,
        whoop_recovery_data.score.hrv_rmssd_milli :: decimal(10, 2) as hrv_rmssd_milli,
        whoop_recovery_data.score.spo2_percentage :: decimal(10, 2) as spo2_percentage,
        whoop_recovery_data.score.skin_temp_celsius :: decimal(10, 2) as skin_temp_celsius

    from whoop_recovery_data
    left join whoop_sleep_data on whoop_recovery_data.sleep_id = whoop_sleep_data.id
)

select * from final
