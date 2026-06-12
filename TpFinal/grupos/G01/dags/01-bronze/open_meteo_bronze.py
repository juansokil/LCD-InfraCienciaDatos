import json
import logging
import os
from datetime import datetime, timedelta

import requests
from airflow.decorators import dag, task
from sqlalchemy import create_engine, text

PROVINCIAS = {
    "buenos_aires":   {"lat": -34.6037, "lon": -58.3816},
    "cordoba":        {"lat": -31.4135, "lon": -64.1811},
    "mendoza":        {"lat": -32.8895, "lon": -68.8458},
    "salta":          {"lat": -24.7859, "lon": -65.4117},
    "tierra_del_fuego": {"lat": -54.8019, "lon": -68.3030},
}

API_URL = "https://api.open-meteo.com/v1/forecast"
API_CURRENT_VARS = ",".join([
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "precipitation",
    "wind_speed_10m",
    "weather_code",
])
API_DAILY_VARS = ",".join([
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "apparent_temperature_min",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
    "weather_code",
])

def get_engine():
 
    host = os.environ.get("SOURCE_DB_HOST", "data_warehouse")
    user = os.environ.get("SOURCE_DB_USER", "weather_user")
    password = os.environ.get("SOURCE_DB_PASS", "weather_pass")
    db = os.environ.get("SOURCE_DB_NAME", "weather_dwh")
    return create_engine(
        f"postgresql+psycopg2://{user}:{password}@{host}:5432/{db}"
    )

default_args = {
    "owner": "G01",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}

@dag(
    dag_id="open_meteo_bronze",
    default_args=default_args,
    start_date=datetime(2026, 5, 1),
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    tags=["prod", "bronze", "weather"],
    is_paused_upon_creation=False,
)
def open_meteo_pipeline_bronze():

    @task()
    def extract(provincia_id: str, coords: dict) -> dict:
        params = {
            "latitude": coords["lat"],
            "longitude": coords["lon"],
            "current": API_CURRENT_VARS,
            "daily": API_DAILY_VARS,
            "timezone": "America/Argentina/Buenos_Aires",
            "forecast_days": 7,
        }
        logging.info(f"Extrayendo datos para {provincia_id}")
        response = requests.get(API_URL, params=params, timeout=15)
        response.raise_for_status()
        return {
            "id_provincia": provincia_id,
            "payload": response.json(),
        }

    @task()
    def load(extracted_data: dict):
        prov_id = extracted_data["id_provincia"]
        payload = extracted_data["payload"]

        query = text("""
            INSERT INTO bronze.open_meteo_raw (id_provincia, payload, source)
            VALUES (:id_provincia, :payload, 'open-meteo')
        """)

        logging.info(f"Cargando Bronze para {prov_id}")
        with get_engine().begin() as conn:
            conn.execute(query, {
                "id_provincia": prov_id,
                "payload": json.dumps(payload),
            })
        logging.info(f"Bronze OK: {prov_id}")

    for prov, coords in PROVINCIAS.items():
        data = extract.override(task_id=f"extract_{prov}")(
            provincia_id=prov, coords=coords
        )
        load.override(task_id=f"load_{prov}")(extracted_data=data)


open_meteo_dag = open_meteo_pipeline_bronze()