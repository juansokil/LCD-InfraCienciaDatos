import json
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pendulum
import requests
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sdk import dag, task
from airflow.timetables.trigger import DeltaTriggerTimetable

log = logging.getLogger(__name__)

# Configuracion
CONN_ID = "warehouse"         
URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_DAYS = 7
MAX_RETRIES = 2              
RUN_EVERY = timedelta(hours=1)

TRIGGER_SILVER = any((Path(__file__).resolve().parent.parent / "02-silver").glob("*.py")) # Se activa solo cuando existe algún .py en dags/02-silver/. 
#Mientras no exista, Bronze termina sin disparar nada.

CITIES = [
    {"city_code": "BUE", "city_name": "Buenos Aires", "province": "Buenos Aires", "latitude": -34.6037, "longitude": -58.3816},
    {"city_code": "COR", "city_name": "Córdoba", "province": "Córdoba", "latitude": -31.4201, "longitude": -64.1888},
    {"city_code": "MDZ", "city_name": "Mendoza", "province": "Mendoza", "latitude": -32.8895, "longitude": -68.8458},
    {"city_code": "SLA", "city_name": "Salta", "province": "Salta", "latitude": -24.7821, "longitude": -65.4232},
    {"city_code": "BRC", "city_name": "San Carlos de Bariloche", "province": "Río Negro", "latitude": -41.1335, "longitude": -71.3103},
]

CURRENT_VARS = [
    "temperature_2m", "relative_humidity_2m", "apparent_temperature",
    "precipitation", "weather_code", "wind_speed_10m",
    "wind_direction_10m", "cloud_cover",
]
DAILY_VARS = [
    "weather_code", "temperature_2m_max", "temperature_2m_min",
    "precipitation_sum", "wind_speed_10m_max",
]

SETUP_SQL = """
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
CREATE TABLE IF NOT EXISTS bronze.open_meteo_raw (
    id              BIGSERIAL PRIMARY KEY,
    city_code       VARCHAR(10)  NOT NULL,
    ingested_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    http_status     INTEGER,
    request_params  JSONB        NOT NULL,
    payload         JSONB,
    error_message   TEXT
);
CREATE INDEX IF NOT EXISTS idx_open_meteo_raw_city_ingested
    ON bronze.open_meteo_raw (city_code, ingested_at DESC);
"""



def build_params(city):
    return {
        "latitude": city["latitude"],
        "longitude": city["longitude"],
        "current": ",".join(CURRENT_VARS),
        "daily": ",".join(DAILY_VARS),
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
        "timezone": "America/Argentina/Buenos_Aires",
        "forecast_days": FORECAST_DAYS,
    }


def fetch(params):
    """GET con timeout y reintentos. Devuelve (http_status, payload|None, error|None)."""
    status, error = None, None
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.get(URL, params=params, timeout=30)
            status = r.status_code
            if status == 200:
                try:
                    return 200, r.json(), None
                except ValueError as e:
                    return 200, None, f"JSON mal formado: {e}"
            error = f"HTTP {status}: {r.text[:300]}"
            if status < 500 and status != 429:
                break  # error del cliente, reintentar no sirve
        except requests.RequestException as e:
            error = f"Error de red: {e}"
        if attempt < MAX_RETRIES:
            time.sleep(2 ** attempt)
    return status, None, error


def validate_payload(payload):
    """Devuelve un mensaje de error si el snapshot es inválido, si está bien, None."""
    if "current" not in payload or "daily" not in payload:
        return "Falta el objeto 'current' o 'daily'"
    missing = [v for v in CURRENT_VARS if v not in payload["current"]]
    missing += [f"daily.{v}" for v in ["time"] + DAILY_VARS if v not in payload["daily"]]
    if missing:
        return f"Campos faltantes: {', '.join(missing)}"
    bad = [k for k in ["time"] + DAILY_VARS if len(payload["daily"][k]) != FORECAST_DAYS]
    if bad:
        return f"Arreglos diarios sin {FORECAST_DAYS} posiciones: {', '.join(bad)}"
    return None


# 
@dag(
    dag_id="open_meteo_bronze",
    schedule=DeltaTriggerTimetable(RUN_EVERY),
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,   # arranca solo, sin activarlo desde la UI
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["open-meteo", "bronze"],
)
def open_meteo_bronze():

    @task
    def extract_bronze():
        hook = PostgresHook(postgres_conn_id=CONN_ID)
        hook.run(SETUP_SQL)  

        ok, failed = [], []
        for city in CITIES:
            params = build_params(city)
            status, payload, error = fetch(params)
            if error is None:
                error = validate_payload(payload)

            
            hook.run(
                """
                INSERT INTO bronze.open_meteo_raw
                    (city_code, ingested_at, http_status, request_params, payload, error_message)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
                """,
                parameters=(
                    city["city_code"],
                    datetime.now(timezone.utc),
                    status,
                    json.dumps(params),
                    json.dumps(payload) if payload is not None else None,
                    error,
                ),
            )
            if error:
                failed.append(city["city_code"])
                log.error("Falló %s: %s", city["city_code"], error)
            else:
                ok.append(city["city_code"])
                log.info("OK %s", city["city_code"])

        log.info("Correctas: %s | Fallidas: %s", ok, failed)
        if not ok:
            raise RuntimeError("Bronze: fallaron todas las ciudades")

    bronze = extract_bronze()

    if TRIGGER_SILVER:
        trigger_silver = TriggerDagRunOperator(
            task_id="trigger_silver",
            trigger_dag_id="open_meteo_silver",
            wait_for_completion=False,
        )
        bronze >> trigger_silver


open_meteo_bronze()
