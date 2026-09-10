with

weather as (
    select * from {{ ref('int_weather_daily') }}
),

final as (
    select

        date_day,
        temperature_max_celsius,
        temperature_min_celsius,
        temperature_mean_celsius,
        apparent_temperature_mean_celsius,
        precipitation_sum_mm,
        rain_sum_mm,
        snowfall_sum_cm,
        precipitation_hours,
        had_precipitation,
        windspeed_max_kmh,
        windgusts_max_kmh,
        wind_direction_dominant_degrees,
        sunshine_duration_hours,
        weathercode,
        et0_evapotranspiration_mm

    from weather
)

select * from final
