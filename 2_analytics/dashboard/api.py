# =====================================================================
# FastAPI backend for serving DuckDB — Sport Analytics Operations Dashboard
# =====================================================================

import duckdb
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .chat_agents import DB_PATH
from .chat_runner import ChatUnavailable, run_chat

DUCKDB_PATH = str(DB_PATH)

app = FastAPI()


def to_json_records(df):
    """DuckDB NULLs surface as NaN in pandas, which json.dumps rejects - swap for None."""
    return df.replace({np.nan: None}).to_dict(orient="records")


# Allow HTML frontend to access API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/recovery")
def get_recovery():
    """Returns the full recovery dataset as JSON."""
    con = duckdb.connect(DUCKDB_PATH, read_only=True)
    df = con.execute(
        """
        SELECT
            date_day,
            recovery_score,
            resting_heart_rate,
            hrv_rmssd_milli,
            spo2_percentage,
            skin_temp_celsius
        FROM marts.fct_whoop_recovery
        WHERE recovery_score IS NOT NULL
        ORDER BY date_day
        """
    ).fetchdf()
    con.close()

    return to_json_records(df)


@app.get("/sleep")
def get_sleep():
    """Returns sleep duration + quality metrics joined by sleep_id, including
    moon phase (already attached per-night via the moon seed join), as JSON."""
    con = duckdb.connect(DUCKDB_PATH, read_only=True)
    df = con.execute(
        """
        SELECT
            s.date_day,
            s.asleep_duration_minutes,
            s.in_bed_duration_minutes,
            s.light_sleep_duration_minutes,
            s.deep_sleep_duration_minutes,
            s.rem_duration_minutes,
            s.awake_duration_minutes,
            q.sleep_performance,
            q.sleep_efficiency,
            q.sleep_consistency,
            q.sleep_debt_minutes,
            q.nap,
            q.moon_phase,
            q.moon_illumination,
            q.moon_phase_cycle
        FROM marts.fct_whoop_sleeps s
        LEFT JOIN marts.fct_whoop_sleep_quality q ON s.sleep_id = q.sleep_id
        WHERE s.asleep_duration_minutes IS NOT NULL
        ORDER BY s.date_day
        """
    ).fetchdf()
    con.close()

    return to_json_records(df)


@app.get("/workouts")
def get_workouts():
    """Returns the full workouts dataset as JSON."""
    con = duckdb.connect(DUCKDB_PATH, read_only=True)
    df = con.execute(
        """
        SELECT
            date_day,
            workout_start_time,
            activity_name,
            is_sport_exercise,
            duration_minutes,
            activity_strain,
            kilojoule,
            average_heart_rate,
            max_heart_rate
        FROM marts.fct_whoop_workouts
        WHERE activity_strain IS NOT NULL
        ORDER BY workout_start_time
        """
    ).fetchdf()
    con.close()

    return to_json_records(df)


@app.get("/weather")
def get_weather():
    """Returns daily local weather."""
    con = duckdb.connect(DUCKDB_PATH, read_only=True)
    df = con.execute(
        """
        SELECT
            date_day,
            temperature_max_celsius,
            temperature_min_celsius,
            temperature_mean_celsius,
            precipitation_sum_mm,
            had_precipitation,
            sunshine_duration_hours,
            weathercode
        FROM marts.fct_weather_daily
        ORDER BY date_day
        """
    ).fetchdf()
    con.close()

    return to_json_records(df)


class ChatRequest(BaseModel):
    message: str
    session_id: str


class ChatResponse(BaseModel):
    answer: str
    sql: str | None = None
    row_count: int | None = None
    truncated: bool = False
    error: str | None = None


@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    """Ask a question about the analytics database. The model only sees query rows."""
    message = body.message.strip()
    session_id = body.session_id.strip()
    if not message or not session_id:
        raise HTTPException(
            status_code=400, detail="Message and session_id are required"
        )

    try:
        result = await run_chat(message, session_id)
    except ChatUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if result.error:
        raise HTTPException(status_code=422, detail=result.error)

    return ChatResponse(
        answer=result.answer,
        sql=result.sql,
        row_count=result.row_count,
        truncated=result.truncated,
        error=None,
    )
