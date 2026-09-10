with

moon_data as (
    select * from {{ ref('mooncalender') }}
),

final as (

    select

        datum :: date as date_day,
        wochentag :: varchar as day_of_week,
        monat :: varchar as month,
        mondphase :: varchar as moon_phase,
        beleuchtung :: decimal(10, 2) as illumination,
        phasenzyklus :: integer as phase_cycle

    from moon_data

)

select * from final
