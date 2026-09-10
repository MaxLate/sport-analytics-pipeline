"""
Thin client for the Open-Meteo API (no API key required).

Two endpoints are used:
- archive-api.open-meteo.com: historical reanalysis data (ERA5), used for a
  one-time deep backfill. Has an ingestion lag of a few days, so it is not
  suitable for "today"/very recent data.
- api.open-meteo.com/v1/forecast with `past_days`: covers today and the
  recent past (up to 92 days back), used for the daily incremental pull.
  Recent-day daily aggregates can be revised as the forecast model updates,
  which is why the loader upserts by date instead of skipping existing rows.
"""

import requests

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

DAILY_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "apparent_temperature_mean",
    "precipitation_sum",
    "rain_sum",
    "snowfall_sum",
    "precipitation_hours",
    "windspeed_10m_max",
    "windgusts_10m_max",
    "winddirection_10m_dominant",
    "sunshine_duration",
    "weathercode",
    "et0_fao_evapotranspiration",
]


def fetch_archive(latitude, longitude, timezone, start_date, end_date):
    """Fetch daily historical weather for [start_date, end_date] (YYYY-MM-DD)."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ",".join(DAILY_VARS),
    }
    response = requests.get(ARCHIVE_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_forecast(latitude, longitude, timezone, past_days=7):
    """Fetch daily weather for the last `past_days` days plus today."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone,
        "past_days": past_days,
        "forecast_days": 1,
        "daily": ",".join(DAILY_VARS),
    }
    response = requests.get(FORECAST_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()
