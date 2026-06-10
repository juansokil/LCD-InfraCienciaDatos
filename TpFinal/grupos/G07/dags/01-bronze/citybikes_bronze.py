"""
DAG Bronze: Ingesta de API CityBikes (Ecobici Buenos Aires)
Pipeline: API -> Landing -> Metadata -> Idempotencia (ts) -> Bronze(Postgres) -> Processed
"""

from airflow.decorators import dag, task
from airflow.operators.python import get_current_context
from datetime import datetime, timedelta
import os
import shutil
import json

# =====================================================
# DIRECTORIOS
# =====================================================

BASE_DIR = "/opt/airflow/data"
LANDING = f"{BASE_DIR}/landing"
PROCESSED = f"{BASE_DIR}/processed"

# =====================================================
# DAG
# =====================================================

@dag(
    dag_id="bronze_citybikes_api",
    start_date=datetime(2024, 1, 1),
    schedule="*/5 * * * *",
    catchup=False,
    is_paused_upon_creation=False,
    tags=["bronze", "citybikes", "ecobici-baires"],
    default_args={
        "retries": 3,
        "retry_delay": timedelta(minutes=5),
        "retry_exponential_backoff": True,
    }
)
def bronze_citybikes_pipeline():

    import requests
    import pandas as pd
    import sqlalchemy
    from datetime import UTC

    @task
    def extraer_y_cargar_bronze():

        ctx = get_current_context()
        ds = ctx["ds"]
        ts = ctx["ts"]

        for d in [LANDING, PROCESSED]:
            os.makedirs(d, exist_ok=True)

        # =================================================
        # EXTRACCIÓN
        # =================================================

        networks_url = "http://api.citybik.es/v2/networks"
        ecobici_url = "http://api.citybik.es/v2/networks/ecobici-buenos-aires"

        networks_response = requests.get(networks_url, timeout=30)
        networks_raw_data = networks_response.json()
        ecobici_response = requests.get(ecobici_url, timeout=30)
        ecobici_raw_data = ecobici_response.json()

        # =================================================
        # LANDING
        # =================================================

        networks_filename = "networks.json"
        ecobici_filename = "ecobici_stations.json"
        networks_landing_path = os.path.join(LANDING, networks_filename)
        ecobici_landing_path = os.path.join(LANDING, ecobici_filename)
 
        with open(networks_landing_path, "w", encoding="utf-8") as f:
            json.dump(networks_raw_data, f, ensure_ascii=False, indent=2)
        with open(ecobici_landing_path, "w", encoding="utf-8") as f:
            json.dump(ecobici_raw_data, f, ensure_ascii=False, indent=2)

        # =================================================
        # NORMALIZACIÓN BRONZE
        # =================================================

        ingested_at = datetime.now(UTC).isoformat()
        network = ecobici_raw_data["network"]
        stations = network["stations"]
        all_networks = networks_raw_data["networks"]

        def normalizar_columnas(dataframe):
            dataframe.columns = [c.strip().replace(" ", "_") for c in dataframe.columns]
            return dataframe

        # convertir estructuras complejas a JSON
        def convertir_estructuras_complejas(dataframe):
            for col in dataframe.columns:
                dataframe[col] = dataframe[col].apply(
                    lambda x: json.dumps(x, ensure_ascii=False) 
                    if isinstance(x, (dict, list)) 
                    else x
                )
            return dataframe

        # =================================================
        # METADATA (Agregamos ts)
        # =================================================

        # Tabla bronze.networks: snapshot de todas las redes disponibles.
        networks_rows = []
        for item in all_networks:
            location = item.get("location", {}) or {}
            networks_rows.append({
                "network_id": item.get("id"),
                "name": item.get("name"),
                "city": location.get("city"),
                "country": location.get("country"),
                "latitude": location.get("latitude"),
                "longitude": location.get("longitude"),
                "href": item.get("href"),
                "ts": ts,
                "ds": ds,
                "source_url": networks_url,
                "ingested_at": ingested_at,
            })

        df_networks = normalizar_columnas(convertir_estructuras_complejas(pd.DataFrame(networks_rows)))

        # Tabla bronze.stations: snapshot de estaciones de EcoBici.
        station_rows = []
        for station in stations:
            extra = station.get("extra", {}) or {}
            station_rows.append({
                "station_id": station.get("id"),
                "network_id": network.get("id"),
                "name": station.get("name"),
                "latitude": station.get("latitude"),
                "longitude": station.get("longitude"),
                "free_bikes": station.get("free_bikes"),
                "empty_slots": station.get("empty_slots"),
                "timestamp_api": station.get("timestamp"),
                "extra_json": json.dumps(extra, ensure_ascii=False),
                "ts": ts,
                "ds": ds,
                "source_url": ecobici_url,
                "ingested_at": ingested_at,
            })

        df_stations = normalizar_columnas(convertir_estructuras_complejas(pd.DataFrame(station_rows)))

        # Tabla bronze.snapshots: trazabilidad de cada request a la API.
        df_snapshots = pd.DataFrame([
            {
                "snapshot_id": f"{ts}__networks",
                "network_id": None,
                "endpoint": "/v2/networks",
                "status_code": networks_response.status_code,
                "response_json": json.dumps(networks_raw_data, ensure_ascii=False),
                "ts": ts,
                "ds": ds,
                "source_url": networks_url,
                "ingested_at": ingested_at,
            },
            {
                "snapshot_id": f"{ts}__ecobici",
                "network_id": network.get("id"),
                "endpoint": "/v2/networks/ecobici-buenos-aires",
                "status_code": ecobici_response.status_code,
                "response_json": json.dumps(ecobici_raw_data, ensure_ascii=False),
                "ts": ts,
                "ds": ds,
                "source_url": ecobici_url,
                "ingested_at": ingested_at,
            }
        ])

        tables = {"networks": df_networks, "stations": df_stations, "snapshots": df_snapshots}

        # =================================================
        # POSTGRES
        # =================================================

        DB_URI = f"postgresql+psycopg2://{os.getenv('SOURCE_DB_USER','admin')}:{os.getenv('SOURCE_DB_PASS','admin')}@{os.getenv('SOURCE_DB_HOST','data_warehouse')}:5432/{os.getenv('SOURCE_DB_NAME','InfraCienciaDatos')}"
        engine = sqlalchemy.create_engine(DB_URI)
        schema_db = "bronze"
        conn = engine.raw_connection()

        try:
            cur = conn.cursor()

            # =============================================
            # CREAR SCHEMA
            # =============================================

            cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_db}";')

            for table, df in tables.items():
                fq_table = f'"{schema_db}"."{table}"'

                # =============================================
                # CREAR TABLA
                # =============================================

                # Agregamos ts a la estructura base
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {fq_table} (
                        ts text,
                        ds text,
                        source_url text,
                        ingested_at text
                    );
                """)
                conn.commit()

                # =============================================
                # EVOLUCIÓN DE ESQUEMA
                # =============================================

                # Ignoramos ts en la evolución dinámica
                for col in df.columns:
                    if col in ("ts", "ds", "source_url", "ingested_at"):
                        continue
                    cur.execute(f'ALTER TABLE {fq_table} ADD COLUMN IF NOT EXISTS "{col}" text;')
                conn.commit()

                # =============================================
                # IDEMPOTENCIA por ts
                # =============================================

                cur.execute(f"DELETE FROM {fq_table} WHERE ts = %s;", (ts,))
                conn.commit()

                # =============================================
                # INSERT
                # =============================================

                insert_cols = list(df.columns)
                cols_sql = ", ".join([f'"{c}"' for c in insert_cols])
                placeholders = ", ".join(["%s"] * len(insert_cols))
                insert_sql = f"INSERT INTO {fq_table} ({cols_sql}) VALUES ({placeholders});"

                df = df.where(pd.notnull(df), None)
                rows = [tuple(row) for row in df[insert_cols].to_numpy()]
                cur.executemany(insert_sql, rows)

            conn.commit()

            # =============================================
            # PROCESSED
            # =============================================

            ds_dir = os.path.join(PROCESSED, f"ds={ds}")
            os.makedirs(ds_dir, exist_ok=True)
            timestamp_str = datetime.now().strftime("%H%M%S")
            shutil.move(networks_landing_path, os.path.join(ds_dir, f"{timestamp_str}__{networks_filename}"))
            shutil.move(ecobici_landing_path, os.path.join(ds_dir, f"{timestamp_str}__{ecobici_filename}"))

            print(f"Ingesta exitosa. Se guardaron {len(df_networks)} redes, {len(df_stations)} estaciones en bronze.")

        finally:
            conn.close()
            engine.dispose()

    extraer_y_cargar_bronze()

dag_instance = bronze_citybikes_pipeline()
