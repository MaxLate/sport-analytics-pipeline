with

weather_data as (
    select * from {{ ref('stg_weather_daily') }}
),

enhanced as (

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
        windspeed_max_kmh,
        windgusts_max_kmh,
        wind_direction_dominant_degrees,
        sunshine_duration_seconds,
        weathercode,
        et0_evapotranspiration_mm,

        precipitation_sum_mm > 0 as had_precipitation,
        sunshine_duration_seconds / 3600.0 as sunshine_duration_hours

    from weather_data
)

select * from enhanced
