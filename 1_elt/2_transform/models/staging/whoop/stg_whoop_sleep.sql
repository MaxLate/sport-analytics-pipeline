with

whoop_sleep_data as (
    select * from {{ source('whoop', 'whoop_sleeps') }}
),

final as (
    select

        id :: varchar as sleep_id,
        start :: timestamp as sleep_onset,
        "end" :: timestamp as wake_onset,
        score.sleep_performance_percentage :: decimal(10, 2) as sleep_performance,
        score.respiratory_rate :: decimal(10, 2) as respiratory_rate,

        score.stage_summary.total_in_bed_time_milli :: bigint as in_bed_time_milli,
        score.stage_summary.total_light_sleep_time_milli :: bigint as light_sleep_time_milli,
        score.stage_summary.total_slow_wave_sleep_time_milli :: bigint as slow_wave_sleep_time_milli,
        score.stage_summary.total_rem_sleep_time_milli :: bigint as rem_sleep_time_milli,
        score.stage_summary.total_awake_time_milli :: bigint as awake_time_milli,

        score.sleep_needed.baseline_milli :: bigint as sleep_need_baseline_milli,
        score.sleep_needed.need_from_sleep_debt_milli :: bigint as sleep_need_from_sleep_debt_milli,
        score.sleep_needed.need_from_recent_strain_milli :: bigint as sleep_need_from_recent_strain_milli,
        score.sleep_needed.need_from_recent_nap_milli :: bigint as sleep_need_from_recent_nap_milli,

        score.sleep_efficiency_percentage :: decimal(10, 2) as sleep_efficiency,
        score.sleep_consistency_percentage :: decimal(10, 2) as sleep_consistency,
        nap :: boolean as nap

    from whoop_sleep_data
)

select * from final
