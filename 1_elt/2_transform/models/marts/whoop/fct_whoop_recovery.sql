with

whoop_recovery as (
    select * from {{ ref('int_whoop_recovery') }}
),

final as (
    select

        whoop_recovery_id,
        date_day,

        -- recovery metrics
        recovery_score,
        resting_heart_rate,
        hrv_rmssd_milli,
        spo2_percentage,
        skin_temp_celsius

    from whoop_recovery
)

select * from final
