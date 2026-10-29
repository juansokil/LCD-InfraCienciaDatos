from airflow.sdk import dag, task
from datetime import datetime, timezone

import os
import requests
import pandas as pd
import sqlalchemy


API_URL = "https://api.citybik.es/v2/networks/ecobici"

RAW_BASE_DIR = "/opt/airflow/data/raw/citybikes_ecobici"


@dag(
    dag_id="citybikes_bronze",
    start_date=datetime(2026, 10, 1),
    schedule="*/5 * * * *",   # cada 5 minutos
    catchup=False,
    is_paused_upon_creation=False,
    tags=["prod", "bronze", "citybikes"],
)
def citybikes_bronze():

    @task
    def ingest_citybikes():

        # -------------------------------------------------
        # 1. Consultar API
        # -------------------------------------------------
        response = requests.get(API_URL, timeout=30)
        response.raise_for_status()

        payload = response.json()

        network = payload["network"]
        stations = network["stations"]

        print(f"Red: {network['name']}")
        print(f"Estaciones recibidas: {len(stations)}")

        # -------------------------------------------------
        # 2. Guardar payload crudo en zona RAW
        # -------------------------------------------------
        now = datetime.now(timezone.utc)

        ds = now.strftime("%Y-%m-%d")
        timestamp_file = now.strftime("%Y%m%dT%H%M%SZ")

        raw_dir = f"{RAW_BASE_DIR}/ds={ds}"
        os.makedirs(raw_dir, exist_ok=True)

        raw_file = f"{raw_dir}/ecobici_{timestamp_file}.json"

        with open(raw_file, "wb") as f:
            f.write(response.content)

        print(f"RAW guardado en: {raw_file}")

        # -------------------------------------------------
        # 3. Construir tabla Bronze
        # -------------------------------------------------
        rows = []

        for station in stations:

            rows.append({
                "network_id": network["id"],
                "network_name": network["name"],
                "station_id": station.get("id"),
                "station_name": station.get("name"),
                "latitude": station.get("latitude"),
                "longitude": station.get("longitude"),
                "station_timestamp": station.get("timestamp"),
                "free_bikes": station.get("free_bikes"),
                "empty_slots": station.get("empty_slots"),
                "ingested_at": now,
            })

        df = pd.DataFrame(rows)

        # -------------------------------------------------
        # 4. Conectar al Data Warehouse
        # -------------------------------------------------
        engine = sqlalchemy.create_engine(
            f"postgresql+psycopg2://"
            f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
            f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
            f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
            f"{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
        )

        # -------------------------------------------------
        # 5. Guardar snapshot en Bronze
        # -------------------------------------------------
        df.to_sql(
            "citybikes_stations",
            engine,
            schema="bronze",
            if_exists="append",
            index=False,
        )

        print(
            f"OK: {len(df)} filas agregadas a "
            "bronze.citybikes_stations"
        )

    ingest_citybikes()


citybikes_bronze()