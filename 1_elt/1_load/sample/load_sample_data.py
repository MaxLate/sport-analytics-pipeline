"""
Load deterministic synthetic WHOOP + weather data into the raw schemas of a
DuckDB warehouse, so the dbt project, dashboard and chat run without a WHOOP
account or network access (demo mode, CI).

The tables have exactly the columns and nested STRUCT types the real load
scripts produce, so dbt cannot tell the difference.

Refuses to touch a warehouse that already holds raw data unless --force is
given, because --force replaces the raw WHOOP and weather tables.

Usage (from repo root):
    python 1_elt/1_load/sample/load_sample_data.py
    python 1_elt/1_load/sample/load_sample_data.py --db-path /tmp/demo.duckdb
"""

import argparse
import math
import os
import random
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd

project_root = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = Path(
    os.environ.get(
        "WAREHOUSE_PATH", project_root / "0_data" / "database" / "warehouse.duckdb"
    )
)

START_DATE = date(2026, 1, 1)
DAYS = 181
USER_ID = 1
SEED = 42

RAW_TABLES = [
    "whoop.whoop_sleeps",
    "whoop.whoop_recoveries",
    "whoop.whoop_workouts",
    "weather.weather_daily",
]

# (WHOOP sport_name, sport_id, typical duration minutes, typical strain)
SPORTS = [
    ("running", 0, 45, 12.0),
    ("trail-running", 0, 70, 14.0),
    ("cycling", 1, 90, 13.0),
    ("weightlifting", 45, 60, 9.0),
    ("hiit", 96, 35, 11.0),
    ("yoga", 44, 50, 4.0),
    ("walking", 63, 40, 5.0),
    ("hiking-rucking", 52, 150, 10.0),
]
SPORT_WEIGHTS = [5, 1, 3, 4, 2, 2, 5, 1]


def _iso(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"


def _offset(day: date) -> str:
    return "+02:00" if date(2026, 3, 29) <= day < date(2026, 10, 25) else "+01:00"


def _uuid(rng: random.Random) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def _build_rows(rng: random.Random) -> dict[str, pd.DataFrame]:
    sleeps, recoveries, workouts, weather = [], [], [], []

    for i in range(DAYS):
        day = START_DATE + timedelta(days=i)
        season = math.sin((i - 20) / 365 * 2 * math.pi)  # -1 in winter, +1 in summer

        # Main sleep: onset the evening before `day` (UTC), 6-8.5 h in bed.
        onset = datetime.combine(
            day - timedelta(days=1), datetime.min.time()
        ) + timedelta(
            hours=21, minutes=rng.randint(0, 150), milliseconds=rng.randint(0, 999)
        )
        in_bed = rng.randint(360, 510) * 60_000
        awake = int(in_bed * rng.uniform(0.04, 0.12))
        asleep = in_bed - awake
        deep = int(asleep * rng.uniform(0.15, 0.25))
        rem = int(asleep * rng.uniform(0.18, 0.28))
        light = asleep - deep - rem
        performance = round(min(100.0, asleep / 27_000_000 * 100), 1)
        sleep_id = _uuid(rng)
        cycle_id = 1_000_000 + i
        took_nap = i % 9 == 4
        sleeps.append(
            {
                "id": sleep_id,
                "cycle_id": cycle_id,
                "start": _iso(onset),
                "end": _iso(onset + timedelta(milliseconds=in_bed)),
                "timezone_offset": _offset(day),
                "nap": False,
                "in_bed": in_bed,
                "awake": awake,
                "light": light,
                "deep": deep,
                "rem": rem,
                "cycles": rng.randint(3, 6),
                "disturbances": rng.randint(2, 14),
                "baseline": 27_000_000,
                "debt": rng.randint(0, 6_000_000),
                "strain_need": rng.randint(0, 3_600_000),
                "nap_need": -rng.randint(600_000, 1_800_000) if took_nap else 0,
                "respiratory_rate": round(rng.uniform(13.0, 15.5), 2),
                "performance": performance,
                "consistency": float(rng.randint(55, 95)),
                "efficiency": round(asleep / in_bed * 100, 2),
            }
        )

        recovery = max(5.0, min(99.0, performance * 0.7 + rng.gauss(0, 12)))
        recoveries.append(
            {
                "cycle_id": cycle_id,
                "sleep_id": sleep_id,
                "created_at": _iso(onset + timedelta(milliseconds=in_bed, minutes=2)),
                "recovery_score": round(recovery),
                "resting_heart_rate": float(rng.randint(50, 66)),
                "hrv": round(25 + recovery * 0.5 + rng.gauss(0, 6), 2),
                "spo2": round(rng.uniform(94.0, 98.0), 2),
                "skin_temp": round(rng.uniform(32.5, 34.0), 2),
            }
        )

        if took_nap:
            nap_onset = datetime.combine(day, datetime.min.time()) + timedelta(
                hours=12, minutes=30
            )
            nap_len = rng.randint(20, 45) * 60_000
            sleeps.append(
                {
                    **sleeps[-1],
                    "id": _uuid(rng),
                    "cycle_id": cycle_id,
                    "start": _iso(nap_onset),
                    "end": _iso(nap_onset + timedelta(milliseconds=nap_len)),
                    "nap": True,
                    "in_bed": nap_len,
                    "awake": nap_len // 5,
                    "light": nap_len - nap_len // 5,
                    "deep": 0,
                    "rem": 0,
                    "nap_need": 0,
                }
            )

        for _ in range(rng.choices([0, 1, 2], weights=[3, 5, 1])[0]):
            name, sport_id, minutes, strain = rng.choices(
                SPORTS, weights=SPORT_WEIGHTS
            )[0]
            duration = max(15, int(rng.gauss(minutes, minutes * 0.2)))
            start = datetime.combine(day, datetime.min.time()) + timedelta(
                hours=rng.choice([6, 12, 16, 17, 18]), minutes=rng.randint(0, 59)
            )
            end = start + timedelta(minutes=duration)
            avg_hr = rng.randint(95, 160)
            zone_ms = duration * 60_000
            distance = (
                round(duration * rng.uniform(140, 200), 1)
                if name in {"running", "trail-running"}
                else (
                    round(duration * rng.uniform(350, 500), 1)
                    if name == "cycling"
                    else None
                )
            )
            workouts.append(
                {
                    "id": _uuid(rng),
                    "created_at": _iso(end + timedelta(minutes=1)),
                    "start": _iso(start),
                    "end": _iso(end),
                    "timezone_offset": _offset(day),
                    "sport_name": name,
                    "sport_id": float(sport_id),
                    "strain": round(max(1.0, rng.gauss(strain, 2.0)), 2),
                    "avg_hr": avg_hr,
                    "max_hr": avg_hr + rng.randint(10, 35),
                    "kilojoule": round(duration * rng.uniform(25, 55), 1),
                    "distance": distance,
                    "altitude_gain": (
                        round(rng.uniform(0, 600), 1) if distance else None
                    ),
                    "z0": int(zone_ms * 0.1),
                    "z1": int(zone_ms * 0.3),
                    "z2": int(zone_ms * 0.3),
                    "z3": int(zone_ms * 0.2),
                    "z4": int(zone_ms * 0.08),
                    "z5": zone_ms - int(zone_ms * 0.98),
                }
            )

        t_mean = 10 + 9 * season + rng.gauss(0, 2.5)
        rain = max(0.0, rng.gauss(1.5, 4.0)) if rng.random() < 0.45 else 0.0
        snow = round(rain * 0.7, 1) if t_mean < 1 else 0.0
        weather.append(
            {
                "date_day": day,
                "temperature_2m_max": round(t_mean + rng.uniform(3, 7), 1),
                "temperature_2m_min": round(t_mean - rng.uniform(3, 7), 1),
                "temperature_2m_mean": round(t_mean, 1),
                "apparent_temperature_mean": round(t_mean - rng.uniform(0, 3), 1),
                "precipitation_sum": round(rain, 1),
                "rain_sum": round(rain - snow, 1),
                "snowfall_sum": snow,
                "precipitation_hours": float(min(24, round(rain * 1.5))),
                "windspeed_10m_max": round(rng.uniform(5, 35), 1),
                "windgusts_10m_max": round(rng.uniform(15, 70), 1),
                "winddirection_10m_dominant": rng.randint(0, 359),
                "sunshine_duration": round(
                    rng.uniform(0, 50_000 if season > 0 else 25_000), 2
                ),
                "weathercode": (
                    rng.choice([0, 1, 2, 3, 61, 63, 71])
                    if rain
                    else rng.choice([0, 1, 2, 3])
                ),
                "et0_fao_evapotranspiration": round(rng.uniform(0.3, 5.0), 2),
                "source_endpoint": "archive",
                "ingested_at": pd.Timestamp("2026-07-01 06:00"),
            }
        )

    return {
        "sleeps": pd.DataFrame(sleeps),
        "recoveries": pd.DataFrame(recoveries),
        "workouts": pd.DataFrame(workouts),
        "weather": pd.DataFrame(weather),
    }


SLEEPS_SQL = f"""
CREATE TABLE whoop.whoop_sleeps AS
SELECT
    id::VARCHAR AS id,
    cycle_id::BIGINT AS cycle_id,
    NULL::INTEGER AS v1_id,
    {USER_ID}::BIGINT AS user_id,
    "end"::VARCHAR AS created_at,
    "end"::VARCHAR AS updated_at,
    start::VARCHAR AS start,
    "end"::VARCHAR AS "end",
    timezone_offset::VARCHAR AS timezone_offset,
    nap::BOOLEAN AS nap,
    'SCORED' AS score_state,
    struct_pack(
        stage_summary := struct_pack(
            total_in_bed_time_milli := in_bed::INTEGER,
            total_awake_time_milli := awake::INTEGER,
            total_no_data_time_milli := 0::INTEGER,
            total_light_sleep_time_milli := light::INTEGER,
            total_slow_wave_sleep_time_milli := deep::INTEGER,
            total_rem_sleep_time_milli := rem::INTEGER,
            sleep_cycle_count := cycles::INTEGER,
            disturbance_count := disturbances::INTEGER
        ),
        sleep_needed := struct_pack(
            baseline_milli := baseline::INTEGER,
            need_from_sleep_debt_milli := debt::INTEGER,
            need_from_recent_strain_milli := strain_need::INTEGER,
            need_from_recent_nap_milli := nap_need::INTEGER
        ),
        respiratory_rate := respiratory_rate::DOUBLE,
        sleep_performance_percentage := performance::DOUBLE,
        sleep_consistency_percentage := consistency::DOUBLE,
        sleep_efficiency_percentage := efficiency::DOUBLE
    ) AS score
FROM sample_sleeps
"""

RECOVERIES_SQL = f"""
CREATE TABLE whoop.whoop_recoveries AS
SELECT
    cycle_id::BIGINT AS cycle_id,
    sleep_id::VARCHAR AS sleep_id,
    {USER_ID}::BIGINT AS user_id,
    created_at::VARCHAR AS created_at,
    created_at::VARCHAR AS updated_at,
    'SCORED' AS score_state,
    struct_pack(
        user_calibrating := false,
        recovery_score := recovery_score::DOUBLE,
        resting_heart_rate := resting_heart_rate::DOUBLE,
        hrv_rmssd_milli := hrv::DOUBLE,
        spo2_percentage := spo2::DOUBLE,
        skin_temp_celsius := skin_temp::DOUBLE
    ) AS score
FROM sample_recoveries
"""

WORKOUTS_SQL = f"""
CREATE TABLE whoop.whoop_workouts AS
SELECT
    id::VARCHAR AS id,
    NULL::INTEGER AS v1_id,
    {USER_ID}::BIGINT AS user_id,
    created_at::VARCHAR AS created_at,
    created_at::VARCHAR AS updated_at,
    start::VARCHAR AS start,
    "end"::VARCHAR AS "end",
    timezone_offset::VARCHAR AS timezone_offset,
    sport_name::VARCHAR AS sport_name,
    'SCORED' AS score_state,
    struct_pack(
        strain := strain::DOUBLE,
        average_heart_rate := avg_hr::INTEGER,
        max_heart_rate := max_hr::INTEGER,
        kilojoule := kilojoule::DOUBLE,
        percent_recorded := 1.0::DOUBLE,
        distance_meter := distance::DOUBLE,
        altitude_gain_meter := altitude_gain::DOUBLE,
        altitude_change_meter := NULL::DOUBLE,
        zone_durations := struct_pack(
            zone_zero_milli := z0::INTEGER,
            zone_one_milli := z1::INTEGER,
            zone_two_milli := z2::INTEGER,
            zone_three_milli := z3::INTEGER,
            zone_four_milli := z4::INTEGER,
            zone_five_milli := z5::INTEGER
        )
    ) AS score,
    sport_id::DOUBLE AS sport_id
FROM sample_workouts
"""

WEATHER_SQL = """
CREATE TABLE weather.weather_daily AS
SELECT
    date_day::DATE AS date_day,
    temperature_2m_max::DOUBLE AS temperature_2m_max,
    temperature_2m_min::DOUBLE AS temperature_2m_min,
    temperature_2m_mean::DOUBLE AS temperature_2m_mean,
    apparent_temperature_mean::DOUBLE AS apparent_temperature_mean,
    precipitation_sum::DOUBLE AS precipitation_sum,
    rain_sum::DOUBLE AS rain_sum,
    snowfall_sum::DOUBLE AS snowfall_sum,
    precipitation_hours::DOUBLE AS precipitation_hours,
    windspeed_10m_max::DOUBLE AS windspeed_10m_max,
    windgusts_10m_max::DOUBLE AS windgusts_10m_max,
    winddirection_10m_dominant::BIGINT AS winddirection_10m_dominant,
    sunshine_duration::DOUBLE AS sunshine_duration,
    weathercode::BIGINT AS weathercode,
    et0_fao_evapotranspiration::DOUBLE AS et0_fao_evapotranspiration,
    source_endpoint::VARCHAR AS source_endpoint,
    ingested_at::TIMESTAMP AS ingested_at
FROM sample_weather
"""


def _raw_data_present(con: duckdb.DuckDBPyConnection) -> list[str]:
    existing = {
        f"{schema}.{name}"
        for schema, name in con.execute(
            "SELECT table_schema, table_name FROM information_schema.tables"
        ).fetchall()
    }
    return [t for t in RAW_TABLES if t in existing]


def load_sample_data(db_path: Path, force: bool = False) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        present = _raw_data_present(con)
        if present and not force:
            raise SystemExit(
                f"{db_path} already has raw data ({', '.join(present)}). "
                "Use --force to replace it with sample data, or pass another --db-path."
            )

        frames = _build_rows(random.Random(SEED))
        con.execute("CREATE SCHEMA IF NOT EXISTS whoop")
        con.execute("CREATE SCHEMA IF NOT EXISTS weather")
        for table in RAW_TABLES:
            con.execute(f"DROP TABLE IF EXISTS {table}")
        for key, sql in [
            ("sleeps", SLEEPS_SQL),
            ("recoveries", RECOVERIES_SQL),
            ("workouts", WORKOUTS_SQL),
            ("weather", WEATHER_SQL),
        ]:
            con.register(f"sample_{key}", frames[key])
            con.execute(sql)
            con.unregister(f"sample_{key}")

        for table in RAW_TABLES:
            count = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            print(f"Loaded {count} rows into {table}")
    finally:
        con.close()
    print(f"Sample data saved to: {db_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace existing raw WHOOP and weather tables",
    )
    args = parser.parse_args()
    load_sample_data(args.db_path.resolve(), force=args.force)


if __name__ == "__main__":
    main()
