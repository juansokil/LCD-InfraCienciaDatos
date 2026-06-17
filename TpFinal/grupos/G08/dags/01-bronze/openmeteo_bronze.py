import json
import os
from datetime import datetime

from airflow.decorators import dag, task


DB_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
    f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
    f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
    f"{os.getenv('SOURCE_DB_NAME', 'TpFinal')}"
)

API_URL = "https://api.open-meteo.com/v1/forecast"

CIUDADES = [
    {"city": "Buenos Aires", "latitude": -34.61, "longitude": -58.38},
    {"city": "Cordoba", "latitude": -31.42, "longitude": -64.18},
    {"city": "Mendoza", "latitude": -32.89, "longitude": -68.83},
]


@dag(
    dag_id="g08_openmeteo_bronze",
    start_date=datetime(2026, 6, 17),
    schedule="@hourly",
    catchup=False,
    is_paused_upon_creation=False,
    tags=["g08", "bronze", "openmeteo"],
)
def openmeteo_bronze():
    @task(retries=2)
    def fetch_and_load_weather_raw():
        import requests
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)
        ingested_at = datetime.utcnow()

        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("CREATE SCHEMA IF NOT EXISTS bronze;"))
            conn.execute(
                sqlalchemy.text(
                    """
                    CREATE TABLE IF NOT EXISTS bronze.weather_raw (
                        id BIGSERIAL PRIMARY KEY,
                        city TEXT NOT NULL,
                        latitude DOUBLE PRECISION NOT NULL,
                        longitude DOUBLE PRECISION NOT NULL,
                        raw_json JSONB NOT NULL,
                        ingested_at TIMESTAMPTZ NOT NULL
                    );
                    """
                )
            )

            for ciudad in CIUDADES:
                params = {
                    "latitude": ciudad["latitude"],
                    "longitude": ciudad["longitude"],
                    "current": (
                        "temperature_2m,relative_humidity_2m,"
                        "apparent_temperature,precipitation,wind_speed_10m"
                    ),
                    "daily": (
                        "temperature_2m_max,temperature_2m_min,"
                        "precipitation_sum"
                    ),
                    "timezone": "America/Argentina/Buenos_Aires",
                    "forecast_days": 3,
                }

                response = requests.get(API_URL, params=params, timeout=30)
                response.raise_for_status()

                conn.execute(
                    sqlalchemy.text(
                        """
                        INSERT INTO bronze.weather_raw
                            (city, latitude, longitude, raw_json, ingested_at)
                        VALUES
                            (:city, :latitude, :longitude, CAST(:raw_json AS JSONB), :ingested_at);
                        """
                    ),
                    {
                        "city": ciudad["city"],
                        "latitude": ciudad["latitude"],
                        "longitude": ciudad["longitude"],
                        "raw_json": json.dumps(response.json()),
                        "ingested_at": ingested_at,
                    },
                )

        print(f"Bronze Open-Meteo: {len(CIUDADES)} respuestas crudas insertadas.")

    fetch_and_load_weather_raw()


openmeteo_bronze()
