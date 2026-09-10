with

weather_data as (
    select * from {{ source('weather', 'weather_daily') }}
),

final as (

    select

        date_day :: date as date_day,
        temperature_2m_max :: decimal(10, 2) as temperature_max_celsius,
        temperature_2m_min :: decimal(10, 2) as temperature_min_celsius,
        temperature_2m_mean :: decimal(10, 2) as temperature_mean_celsius,
        apparent_temperature_mean :: decimal(10, 2) as apparent_temperature_mean_celsius,
        precipitation_sum :: decimal(10, 2) as precipitation_sum_mm,
        rain_sum :: decimal(10, 2) as rain_sum_mm,
        snowfall_sum :: decimal(10, 2) as snowfall_sum_cm,
        precipitation_hours :: decimal(10, 2) as precipitation_hours,
        windspeed_10m_max :: decimal(10, 2) as windspeed_max_kmh,
        windgusts_10m_max :: decimal(10, 2) as windgusts_max_kmh,
        winddirection_10m_dominant :: integer as wind_direction_dominant_degrees,
        sunshine_duration :: decimal(10, 2) as sunshine_duration_seconds,
        weathercode :: integer as weathercode,
        et0_fao_evapotranspiration :: decimal(10, 2) as et0_evapotranspiration_mm,
        source_endpoint :: varchar as source_endpoint

    from weather_data

)

select * from final
