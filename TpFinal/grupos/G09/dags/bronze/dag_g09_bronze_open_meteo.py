"""
DAG Bronze G09: ingesta de Open-Meteo, en DOS DAGs que escriben en la misma tabla.

  1) g09_bronze_open_meteo         @hourly -> pipeline vivo (forecast: actual + pronóstico).
  2) g09_bronze_history_backfill   @once   -> carga inicial histórica (ERA5), para tener
                                              años de datos (días de calor extremo, heladas).

Ambos emiten el mismo asset: cuando Bronze termina, Silver y luego Gold arrancan solos.
Idempotencia: UNIQUE (location_id, snapshot_ts) + ON CONFLICT.
"""

from datetime import datetime, timedelta, timezone
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

FORECAST_API_URL = "https://api.open-meteo.com/v1/forecast"
HISTORICAL_API_URL = "https://archive-api.open-meteo.com/v1/archive"

TIMEZONE = "America/Argentina/Buenos_Aires"

PAST_DAYS = int(os.getenv("G09_PAST_DAYS", "7"))
FORECAST_DAYS = int(os.getenv("G09_FORECAST_DAYS", "7"))

HISTORY_START_DATE = os.getenv("G09_HISTORY_START_DATE", "2020-01-01")
HISTORY_END_OFFSET_DAYS = 5  # ERA5 publica con ~5 días de retraso

HOURLY_VARIABLES = [
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation",
    "weather_code",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
]

LOCATIONS = [
    {"location_id": "mar_del_plata", "city": "Mar del Plata", "region_type": "Costa",
     "latitude": -38.0055, "longitude": -57.5426},
    {"location_id": "tandil", "city": "Tandil", "region_type": "Interior",
     "latitude": -37.3217, "longitude": -59.1332},
    {"location_id": "bahia_blanca", "city": "Bahía Blanca", "region_type": "Sur",
     "latitude": -38.7196, "longitude": -62.2724},
]

INSERT_SQL_DO_UPDATE = """
    INSERT INTO bronze.open_meteo_raw (
        snapshot_ts, location_id, city, region_type,
        requested_latitude, requested_longitude,
        api_url, request_params, response_payload
    )
    VALUES (
        :snapshot_ts, :location_id, :city, :region_type,
        :latitude, :longitude,
        :api_url, CAST(:request_params AS JSONB), CAST(:response_payload AS JSONB)
    )
    ON CONFLICT (location_id, snapshot_ts) DO UPDATE SET
        request_params = EXCLUDED.request_params,
        response_payload = EXCLUDED.response_payload,
        ingested_at = NOW()
"""

INSERT_SQL_DO_NOTHING = INSERT_SQL_DO_UPDATE.split("ON CONFLICT")[0] + \
    "ON CONFLICT (location_id, snapshot_ts) DO NOTHING"


def get_database_engine():
    database_url = URL.create(
        drivername="postgresql+psycopg2",
        username=os.environ["SOURCE_DB_USER"],
        password=os.environ["SOURCE_DB_PASS"],
        host=os.getenv("SOURCE_DB_HOST", "data_warehouse"),
        port=int(os.getenv("SOURCE_DB_PORT", "5432")),
        database=os.environ["SOURCE_DB_NAME"],
    )
    return create_engine(database_url, pool_pre_ping=True)


def _create_bronze_table():
    """Compartida por los dos DAGs. El advisory lock evita la carrera de CREATE TABLE."""
    engine = get_database_engine()
    statements = [
        "CREATE SCHEMA IF NOT EXISTS bronze",
        """
        CREATE TABLE IF NOT EXISTS bronze.open_meteo_raw (
            ingestion_id BIGSERIAL PRIMARY KEY,
            snapshot_ts TIMESTAMPTZ NOT NULL,
            location_id VARCHAR(50) NOT NULL,
            city VARCHAR(100) NOT NULL,
            region_type VARCHAR(30) NOT NULL,
            requested_latitude DOUBLE PRECISION NOT NULL,
            requested_longitude DOUBLE PRECISION NOT NULL,
            api_url TEXT NOT NULL,
            request_params JSONB NOT NULL,
            response_payload JSONB NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_open_meteo_raw_snapshot UNIQUE (location_id, snapshot_ts)
        )
        """,
    ]
    try:
        with engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(90901)"))
            for statement in statements:
                connection.execute(text(statement))
    finally:
        engine.dispose()


def _validate_hourly(payload):
    if payload.get("error"):
        raise RuntimeError(payload.get("reason", "Error de Open-Meteo"))
    hourly = payload.get("hourly")
    if not hourly or not hourly.get("time"):
        raise ValueError("La respuesta no contiene datos horarios.")
    n = len(hourly["time"])
    for variable in HOURLY_VARIABLES:
        if len(hourly.get(variable, [])) != n:
            raise ValueError(f"Variable '{variable}' incompleta en la respuesta.")
    return n


def _insert_raw(sql, location, snapshot_ts, api_url, params, payload):
    engine = get_database_engine()
    try:
        with engine.begin() as connection:
            connection.execute(
                text(sql),
                {
                    "snapshot_ts": snapshot_ts,
                    "location_id": location["location_id"],
                    "city": location["city"],
                    "region_type": location["region_type"],
                    "latitude": location["latitude"],
                    "longitude": location["longitude"],
                    "api_url": api_url,
                    "request_params": json.dumps(params),
                    "response_payload": json.dumps(payload),
                },
            )
    finally:
        engine.dispose()


# --------------------------------------------------
# DAG 1: INGESTA HORARIA (forecast)
# --------------------------------------------------

@dag(
    dag_id="g09_bronze_open_meteo",
    description="Ingesta horaria de Open-Meteo (actual + pronóstico) para G09",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=30),
    tags=["g09", "bronze", "open-meteo"],
)
def g09_bronze_open_meteo():

    @task
    def create_bronze_table():
        _create_bronze_table()

    @task(
        retries=3,
        retry_delay=timedelta(minutes=2),
        retry_exponential_backoff=True,
        max_retry_delay=timedelta(minutes=15),
    )
    def ingest_forecast_hourly(location):
        # Snapshot redondeado a la hora: clave de idempotencia.
        snapshot_ts = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

        params = {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "hourly": ",".join(HOURLY_VARIABLES),
            "past_days": PAST_DAYS,
            "forecast_days": FORECAST_DAYS,
            "timezone": TIMEZONE,
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
            "timeformat": "iso8601",
        }

        response = requests.get(FORECAST_API_URL, params=params, timeout=(10, 60))
        response.raise_for_status()
        payload = response.json()
        n = _validate_hourly(payload)

        _insert_raw(INSERT_SQL_DO_UPDATE, location, snapshot_ts, FORECAST_API_URL, params, payload)

        return (
            f"{location['city']}: {n} horas "
            f"({PAST_DAYS}d pasados + {FORECAST_DAYS}d pronóstico), "
            f"snapshot {snapshot_ts.isoformat()}"
        )

    @task(outlets=[BRONZE_ASSET])
    def publish_bronze_asset():
        print("Bronze completo: Silver puede arrancar.")

    create_bronze_table() >> ingest_forecast_hourly.expand(location=LOCATIONS) >> publish_bronze_asset()


# --------------------------------------------------
# DAG 2: CARGA INICIAL HISTÓRICA (ERA5), una sola vez
# --------------------------------------------------

@dag(
    dag_id="g09_bronze_history_backfill",
    description="Carga inicial histórica ERA5 (una sola vez)",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    schedule="@once",
    catchup=False,
    max_active_runs=1,
    tags=["g09", "bronze", "backfill"],
)
def g09_bronze_history_backfill():

    @task
    def create_bronze_table_bf():
        _create_bronze_table()

    @task(
        retries=3,
        retry_delay=timedelta(minutes=5),
        retry_exponential_backoff=True,
        max_retry_delay=timedelta(minutes=30),
    )
    def ingest_history_backfill(location):
        # Guard de idempotencia: si la ciudad ya tiene histórico, no se repite.
        engine = get_database_engine()
        try:
            with engine.connect() as conn:
                exists = conn.execute(
                    text("""SELECT 1 FROM bronze.open_meteo_raw
                            WHERE location_id = :loc AND api_url = :api LIMIT 1"""),
                    {"loc": location["location_id"], "api": HISTORICAL_API_URL},
                ).fetchone()
        finally:
            engine.dispose()
        if exists:
            return f"{location['city']}: histórico ya cargado, se omite."

        end_date = datetime.now(timezone.utc).date() - timedelta(days=HISTORY_END_OFFSET_DAYS)
        start_date = datetime.strptime(HISTORY_START_DATE, "%Y-%m-%d").date()
        if start_date >= end_date:
            raise ValueError("Rango histórico inválido.")

        params = {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "hourly": ",".join(HOURLY_VARIABLES),
            "timezone": TIMEZONE,
            "models": "era5",
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
        }

        response = requests.get(HISTORICAL_API_URL, params=params, timeout=(15, 180))
        response.raise_for_status()
        payload = response.json()
        n = _validate_hourly(payload)

        # snapshot_ts fijo en el pasado: no choca con los snapshots horarios y
        # Silver lo marca como dato medido (no pronóstico).
        _insert_raw(
            INSERT_SQL_DO_NOTHING, location, datetime(2000, 1, 1, tzinfo=timezone.utc),
            HISTORICAL_API_URL, params, payload,
        )
        return f"{location['city']}: {n} horas ({start_date} a {end_date})"

    @task(outlets=[BRONZE_ASSET])
    def publish_history_asset():
        print("Histórico cargado: Silver puede arrancar.")

    create_bronze_table_bf() >> ingest_history_backfill.expand(location=LOCATIONS) >> publish_history_asset()


g09_bronze_history_backfill()
g09_bronze_open_meteo()