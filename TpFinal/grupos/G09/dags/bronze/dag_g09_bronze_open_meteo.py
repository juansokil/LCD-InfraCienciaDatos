"""
DAG Bronze G09: ingesta RECURRENTE de Open-Meteo.

Qué cambió respecto de la versión anterior y por qué (sugerencia del docente):
  - ANTES: Solo usábamos la API de forecast (past_days=7). El dashboard se quedaba
    sin historia y los gráficos de "extremos por año" quedaban vacíos.
  - AHORA: El DAG tiene dos ramas paralelas que alimentan la misma tabla Bronze:
    1. ingest_history_backfill: Usa la API histórica (ERA5) UNA SOLA VEZ para traer
       años de datos (desde 2020) y que el dashboard tenga historia real.
    2. ingest_forecast_hourly: Usa la API de forecast cada hora para traer el clima
       actual y los próximos 7 días (el pipeline "vivo").
  - Ambas APIs devuelven el JSON con la misma clave 'hourly', por lo que Silver
    procesa la historia y el pronóstico exactamente igual, sin cambiar código.
  - Idempotencia: El backfill histórico verifica si ya se hizo (buscando su URL
    en la tabla) y si ya existe, no vuelve a pedir los datos.
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

# URLs de las dos APIs de Open-Meteo
FORECAST_API_URL = "https://api.open-meteo.com/v1/forecast"
HISTORICAL_API_URL = "https://archive-api.open-meteo.com/v1/archive"

TIMEZONE = "America/Argentina/Buenos_Aires"

# Parámetros del Forecast
PAST_DAYS = int(os.getenv("G09_PAST_DAYS", "7"))
FORECAST_DAYS = int(os.getenv("G09_FORECAST_DAYS", "7"))

# Parámetros del Histórico (Backfill)
HISTORY_START_DATE = os.getenv("G09_HISTORY_START_DATE", "2020-01-01")
# ERA5 tarda ~5 días en publicar, así que pedimos hasta hace 5 días.
HISTORY_END_OFFSET_DAYS = 5 

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


# --------------------------------------------------
# DAG
# --------------------------------------------------

@dag(
    dag_id="g09_bronze_open_meteo",
    description="Ingesta de Open-Meteo: Backfill histórico (1 vez) + Forecast (cada hora)",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=45), # Le damos margen por si el backfill tarda
    tags=["g09", "bronze", "open-meteo"],
)
def g09_bronze_open_meteo():

    @task
    def create_bronze_table():
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
                for statement in statements:
                    connection.execute(text(statement))
        finally:
            engine.dispose()

    @task(
        retries=2,
        retry_delay=timedelta(minutes=5),
        retry_exponential_backoff=True,
        max_retry_delay=timedelta(minutes=15),
    )
    def ingest_history_backfill(location):
        """Carga inicial usando la API histórica. Corre solo si la ciudad no tiene histórico."""
        engine = get_database_engine()
        
        # Verificamos si ya tenemos el histórico de esta locación
        with engine.connect() as conn:
            exists = conn.execute(text("""
                SELECT 1 FROM bronze.open_meteo_raw 
                WHERE location_id = :loc AND api_url = :api LIMIT 1
            """), {"loc": location["location_id"], "api": HISTORICAL_API_URL}).fetchone()
            
        if exists:
            engine.dispose()
            return f"{location['city']}: Histórico ya existe, saltando backfill."

        # Calculamos fechas para la API histórica
        today = datetime.now(timezone.utc).date()
        end_date = today - timedelta(days=HISTORY_END_OFFSET_DAYS)
        start_date = datetime.strptime(HISTORY_START_DATE, "%Y-%m-%d").date()
        
        if start_date >= end_date:
            engine.dispose()
            return f"{location['city']}: Rango histórico inválido o ya alcanzado."

        params = {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "hourly": ",".join(HOURLY_VARIABLES),
            "timezone": TIMEZONE,
            "models": "era5", # Modelo histórico requerido por archive-api
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
        }

        response = requests.get(HISTORICAL_API_URL, params=params, timeout=(15, 180))
        response.raise_for_status()
        payload = response.json()

        if "hourly" not in payload or not payload["hourly"].get("time"):
            raise ValueError("La respuesta histórica no contiene datos horarios válidos.")

        # Usamos un snapshot_ts fijo en el pasado (o el inicio del histórico) 
        # para que no choque con el snapshot_ts del forecast de esta misma hora.
        # Al ser (location_id, snapshot_ts) único, esto asegura idempotencia.
        snapshot_ts = datetime(2000, 1, 1, tzinfo=timezone.utc)

        insert_sql = text("""
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
            ON CONFLICT (location_id, snapshot_ts) DO NOTHING
        """)

        try:
            with engine.begin() as connection:
                connection.execute(
                    insert_sql,
                    {
                        "snapshot_ts": snapshot_ts,
                        "location_id": location["location_id"],
                        "city": location["city"],
                        "region_type": location["region_type"],
                        "latitude": location["latitude"],
                        "longitude": location["longitude"],
                        "api_url": HISTORICAL_API_URL,
                        "request_params": json.dumps(params),
                        "response_payload": json.dumps(payload),
                    },
                )
        finally:
            engine.dispose()

        return f"{location['city']}: Histórico cargado desde {start_date} a {end_date}"

    @task(
        retries=3,
        retry_delay=timedelta(minutes=2),
        retry_exponential_backoff=True,
        max_retry_delay=timedelta(minutes=15),
    )
    def ingest_forecast_hourly(location):
        """Ingesta horaria del clima actual + pronóstico."""
        snapshot_ts = datetime.now(timezone.utc).replace(
            minute=0, second=0, microsecond=0
        )

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

        if payload.get("error"):
            raise RuntimeError(payload.get("reason", "Error de Open-Meteo"))

        hourly = payload.get("hourly")
        if not hourly or "time" not in hourly:
            raise ValueError("La respuesta no contiene datos horarios.")

        n = len(hourly["time"])
        for variable in HOURLY_VARIABLES:
            if len(hourly.get(variable, [])) != n:
                raise ValueError(f"Variable '{variable}' incompleta en la respuesta.")

        insert_sql = text("""
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
        """)

        engine = get_database_engine()
        try:
            with engine.begin() as connection:
                connection.execute(
                    insert_sql,
                    {
                        "snapshot_ts": snapshot_ts,
                        "location_id": location["location_id"],
                        "city": location["city"],
                        "region_type": location["region_type"],
                        "latitude": location["latitude"],
                        "longitude": location["longitude"],
                        "api_url": FORECAST_API_URL,
                        "request_params": json.dumps(params),
                        "response_payload": json.dumps(payload),
                    },
                )
        finally:
            engine.dispose()

        return (
            f"{location['city']}: {n} horas "
            f"({PAST_DAYS}d pasados + {FORECAST_DAYS}d pronóstico), "
            f"snapshot {snapshot_ts.isoformat()}"
        )

    @task(outlets=[BRONZE_ASSET])
    def publish_bronze_asset():
        print("Bronze completo (histórico inicial + snapshot actual): Silver puede arrancar.")

    # --------------------------------------------------
    # GRAFO DE DEPENDENCIAS
    # --------------------------------------------------
    table_ready = create_bronze_table()
    
    # Ambas ramas corren en paralelo. 
    # El backfill solo descargará datos la primera vez.
    # El forecast siempre traerá el snapshot de esta hora.
    backfill_tasks = ingest_history_backfill.expand(location=LOCATIONS)
    forecast_tasks = ingest_forecast_hourly.expand(location=LOCATIONS)
    
    # El asset se emite recién cuando ambas ramas terminaron bien
    table_ready >> [backfill_tasks, forecast_tasks] >> publish_bronze_asset()


g09_bronze_open_meteo()