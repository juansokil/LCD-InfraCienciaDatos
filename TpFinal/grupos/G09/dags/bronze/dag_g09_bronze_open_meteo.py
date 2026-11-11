
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import json
import os

import requests

from airflow.sdk import dag, task, Asset

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


# --------------------------------------------------
# CONFIGURACION
# --------------------------------------------------

BRONZE_ASSET = Asset(
    name="g09_bronze_open_meteo_raw",
    uri="postgres://data_warehouse:5432/InfraCienciaDatos/bronze/open_meteo_raw",
)

API_URL = "https://archive-api.open-meteo.com/v1/archive"

TIMEZONE = "America/Argentina/Buenos_Aires"

START_DATE = os.getenv("G09_START_DATE", "2015-01-01")

END_DATE_OVERRIDE = os.getenv("G09_END_DATE")

DAILY_VARIABLES = [
    "temperature_2m_mean",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_hours",
    "relative_humidity_2m_mean",
    "wind_speed_10m_mean",
    "wind_speed_10m_max",
    "wind_direction_10m_dominant",
    "cloud_cover_mean",
]

LOCATIONS = [
    {
        "location_id": "mar_del_plata",
        "city": "Mar del Plata",
        "region_type": "Costa",
        "latitude": -38.0055,
        "longitude": -57.5426,
    },
    {
        "location_id": "tandil",
        "city": "Tandil",
        "region_type": "Interior",
        "latitude": -37.3217,
        "longitude": -59.1332,
    },
    {
        "location_id": "bahia_blanca",
        "city": "Bahía Blanca",
        "region_type": "Sur",
        "latitude": -38.7196,
        "longitude": -62.2724,
    },
]


def get_date_range():

    start = datetime.strptime(
        START_DATE, "%Y-%m-%d"
    ).date()

    if END_DATE_OVERRIDE:
        end = datetime.strptime(
            END_DATE_OVERRIDE, "%Y-%m-%d"
        ).date()
    else:
        today = datetime.now(
            ZoneInfo(TIMEZONE)
        ).date()

        # ERA5 tiene un retraso de publicacion.
        end = today - timedelta(days=5)

    if start > end:
        raise ValueError("El rango de fechas es inválido.")

    return start.isoformat(), end.isoformat()


def get_database_engine():

    database_url = URL.create(
        drivername="postgresql+psycopg2",
        username=os.environ["SOURCE_DB_USER"],
        password=os.environ["SOURCE_DB_PASS"],
        host=os.getenv(
            "SOURCE_DB_HOST", "data_warehouse"
        ),
        port=int(os.getenv("SOURCE_DB_PORT", "5432")),
        database=os.environ["SOURCE_DB_NAME"],
    )

    return create_engine(
        database_url,
        pool_pre_ping=True
    )


# --------------------------------------------------
# DAG
# --------------------------------------------------

@dag(
    dag_id="g09_bronze_open_meteo",
    description="Ingesta histórica de Open-Meteo para G09",
    start_date=datetime(
        2026, 1, 1, tzinfo=timezone.utc
    ),
    schedule="@once",
    catchup=False,
    max_active_runs=1,
    tags=["g09", "bronze", "open-meteo"],
)
def g09_bronze_open_meteo():

    # ----------------------------------------------
    # TAREA 1: CREAR TABLA
    # ----------------------------------------------

    @task
    def create_bronze_table():

        engine = get_database_engine()

        statements = [
            """
            CREATE SCHEMA IF NOT EXISTS bronze
            """,
            """
            CREATE TABLE IF NOT EXISTS bronze.open_meteo_raw (
                ingestion_id BIGSERIAL PRIMARY KEY,
                location_id VARCHAR(50) NOT NULL,
                city VARCHAR(100) NOT NULL,
                region_type VARCHAR(30) NOT NULL,
                requested_latitude DOUBLE PRECISION NOT NULL,
                requested_longitude DOUBLE PRECISION NOT NULL,
                requested_start_date DATE NOT NULL,
                requested_end_date DATE NOT NULL,
                api_url TEXT NOT NULL,
                request_params JSONB NOT NULL,
                response_payload JSONB NOT NULL,
                ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
        ]

        try:
            with engine.begin() as connection:
                for statement in statements:
                    connection.execute(text(statement))
        finally:
            engine.dispose()

    # ----------------------------------------------
    # TAREA 2: INGESTAR UNA LOCALIDAD
    # ----------------------------------------------

    @task(
        retries=2,
        retry_delay=timedelta(minutes=5)
    )
    def ingest_location(location):

        start_date, end_date = get_date_range()

        params = {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "start_date": start_date,
            "end_date": end_date,
            "daily": ",".join(DAILY_VARIABLES),
            "timezone": TIMEZONE,
            "models": "era5",
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
            "timeformat": "iso8601",
            "cell_selection": "land",
        }

        # Consultar API
        response = requests.get(
            API_URL,
            params=params,
            timeout=(15, 180)
        )

        response.raise_for_status()

        payload = response.json()

        if payload.get("error"):
            raise RuntimeError(
                payload.get("reason", "Error de Open-Meteo")
            )

        if "daily" not in payload:
            raise ValueError(
                "La respuesta no contiene datos diarios."
            )

        # Insertar respuesta original en PostgreSQL
        insert_sql = text("""
            INSERT INTO bronze.open_meteo_raw (
                location_id,
                city,
                region_type,
                requested_latitude,
                requested_longitude,
                requested_start_date,
                requested_end_date,
                api_url,
                request_params,
                response_payload
            )
            VALUES (
                :location_id,
                :city,
                :region_type,
                :latitude,
                :longitude,
                :start_date,
                :end_date,
                :api_url,
                CAST(:request_params AS JSONB),
                CAST(:response_payload AS JSONB)
            )
        """)

        engine = get_database_engine()

        try:
            with engine.begin() as connection:
                connection.execute(
                    insert_sql,
                    {
                        "location_id": location["location_id"],
                        "city": location["city"],
                        "region_type": location["region_type"],
                        "latitude": location["latitude"],
                        "longitude": location["longitude"],
                        "start_date": start_date,
                        "end_date": end_date,
                        "api_url": API_URL,
                        "request_params": json.dumps(params),
                        "response_payload": json.dumps(payload),
                    }
                )
        finally:
            engine.dispose()

        return (
            f"{location['city']}: "
            f"{len(payload['daily']['time'])} días guardados."
        )

    # ----------------------------------------------
    # DEPENDENCIAS
    # ----------------------------------------------

    @task(outlets=[BRONZE_ASSET])
    def publish_bronze_asset():
        print("Bronze completo: Silver puede arrancar.")

    table_ready = create_bronze_table()

    ingestions = ingest_location.expand(
        location=LOCATIONS
    )

    table_ready >> ingestions >> publish_bronze_asset()

g09_bronze_open_meteo()