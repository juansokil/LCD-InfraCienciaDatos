import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text


DB_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:{os.getenv('SOURCE_DB_PASS', 'admin')}"
    f"@{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432"
    f"/{os.getenv('SOURCE_DB_NAME', 'TpFinal')}"
)


@st.cache_resource
def get_engine():
    return create_engine(DB_URI)


@st.cache_data(ttl=60)
def run_query(sql: str) -> pd.DataFrame:
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        return pd.DataFrame(result.fetchall(), columns=list(result.keys()))


@st.cache_data(ttl=60)
def table_exists(schema: str, table: str) -> bool:
    engine = get_engine()
    query = text(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = :schema
              AND table_name = :table
        )
        """
    )
    with engine.connect() as conn:
        return bool(conn.execute(query, {"schema": schema, "table": table}).scalar())


def load_weather_daily_summary() -> pd.DataFrame:
    if not table_exists("gold", "weather_daily_summary"):
        return pd.DataFrame()

    return run_query(
        """
        SELECT
            city,
            forecast_date,
            avg_temperature,
            max_temperature,
            min_temperature,
            temperature_range,
            total_precipitation,
            rainy_hours,
            avg_wind_speed,
            max_wind_speed,
            hourly_records,
            weather_category,
            outdoor_score,
            outdoor_recommendation,
            updated_at
        FROM gold.weather_daily_summary
        ORDER BY forecast_date, city
        """
    )
