from airflow.sdk import dag, task
from datetime import datetime, timezone

import os
import requests
import pandas as pd
import sqlalchemy

from sqlalchemy.dialects.postgresql import JSONB


API_URL = "https://api.citybik.es/v2/networks/ecobici"

RAW_BASE_DIR = "/opt/airflow/data/raw/citybikes_ecobici"


@dag(
    dag_id="citybikes_bronze",
    start_date=datetime(2026, 10, 1),
    schedule="*/5 * * * *", 
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

        location = network.get("location") or {}

        print(f"Red: {network.get('name')}")
        print(f"Estaciones recibidas: {len(stations)}")


        extra_keys = sorted({
            key
            for station in stations
            for key in (station.get("extra") or {}).keys()
        })

        print(f"Campos encontrados en extra: {extra_keys}")

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

        # Identificador común para todas las estaciones
        # pertenecientes a esta corrida / snapshot
        snapshot_id = timestamp_file

        # -------------------------------------------------
        # 3. Construir tabla Bronze
        # -------------------------------------------------
        rows = []

        for station in stations:

            extra = station.get("extra") or {}

            uid = extra.get("uid")

            provider_last_updated = extra.get("last_updated")

            rows.append({

                # -----------------------------------------
                # Metadata de la red
                # -----------------------------------------
                "network_id": network.get("id"),
                "network_name": network.get("name"),

                "network_city": location.get("city"),
                "network_country": location.get("country"),
                "network_latitude": location.get("latitude"),
                "network_longitude": location.get("longitude"),

                "network_href": network.get("href"),
                "network_gbfs_href": network.get("gbfs_href"),

                # Puede venir como lista, por eso se
                # conservará como JSONB
                "network_company": network.get("company"),

                # También preservamos cualquier metadata
                # del campo source
                "network_source": network.get("source"),

                # -----------------------------------------
                # Identificación de estación
                # -----------------------------------------
                "station_id": station.get("id"),

                # UID propio del operador
                "station_uid": (
                    str(uid)
                    if uid is not None
                    else None
                ),

                "station_name": station.get("name"),

                # -----------------------------------------
                # Geolocalización
                # -----------------------------------------
                "latitude": station.get("latitude"),
                "longitude": station.get("longitude"),

                # -----------------------------------------
                # Tiempo reportado por CityBikes
                # -----------------------------------------
                "station_timestamp": station.get("timestamp"),

                # Tiempo de actualización informado
                # dentro de extra
                "provider_last_updated": (
                    str(provider_last_updated)
                    if provider_last_updated is not None
                    else None
                ),

                # -----------------------------------------
                # Disponibilidad
                # -----------------------------------------
                "free_bikes": station.get("free_bikes"),
                "empty_slots": station.get("empty_slots"),
                "slots": extra.get("slots"),

                # -----------------------------------------
                # Estado operativo
                # -----------------------------------------
                "renting": extra.get("renting"),
                "returning_allowed": extra.get("returning"),

                "virtual": extra.get("virtual"),

                # Otros posibles estados del estándar /
                # proveedores CityBikes.
                # Si EcoBici no los devuelve, quedan NULL.
                "installed": extra.get("installed"),
                "locked": extra.get("locked"),
                "status": extra.get("status"),

                # -----------------------------------------
                # Bicicletas eléctricas
                # -----------------------------------------
                # Los dejamos disponibles aunque actualmente
                # EcoBici pueda no informarlos.
                "ebikes": extra.get("ebikes"),
                "has_ebikes": extra.get("has_ebikes"),
                "normal_bikes": extra.get("normal_bikes"),

                # -----------------------------------------
                # Información descriptiva
                # -----------------------------------------
                "address": extra.get("address"),

                # -----------------------------------------
                # Medios / terminales de pago
                # -----------------------------------------
                "payment_terminal": extra.get("payment-terminal"),

                # Puede ser lista u otra estructura:
                # se guarda JSONB.
                "payment": extra.get("payment"),

                # -----------------------------------------
                # Preservación completa
                # -----------------------------------------
                # Todo el objeto extra tal como llega.
                "raw_extra": extra,

                # Toda la estación tal como llega desde API.
                "raw_station": station,

                # -----------------------------------------
                # Metadata técnica de nuestra ingesta
                # -----------------------------------------
                "source_url": API_URL,

                "http_status_code": response.status_code,

                "snapshot_id": snapshot_id,

                "raw_file_path": raw_file,

                "ingested_at": now,
            })

        df = pd.DataFrame(rows)

        print(f"Columnas Bronze: {list(df.columns)}")
        print(f"Filas Bronze generadas: {len(df)}")

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
        # 5. Asegurar schema Bronze
        # -------------------------------------------------
        with engine.begin() as conn:
            conn.execute(
                sqlalchemy.text(
                    "CREATE SCHEMA IF NOT EXISTS bronze;"
                )
            )

        # -------------------------------------------------
        # 6. Asegurar estructura de tabla Bronze
        # -------------------------------------------------
        inspector = sqlalchemy.inspect(engine)

        if inspector.has_table(
            "citybikes_stations",
            schema="bronze"
        ):

            with engine.begin() as conn:

                conn.execute(
                    sqlalchemy.text("""
                        ALTER TABLE bronze.citybikes_stations

                        ADD COLUMN IF NOT EXISTS
                            network_city TEXT,

                        ADD COLUMN IF NOT EXISTS
                            network_country TEXT,

                        ADD COLUMN IF NOT EXISTS
                            network_latitude DOUBLE PRECISION,

                        ADD COLUMN IF NOT EXISTS
                            network_longitude DOUBLE PRECISION,

                        ADD COLUMN IF NOT EXISTS
                            network_href TEXT,

                        ADD COLUMN IF NOT EXISTS
                            network_gbfs_href TEXT,

                        ADD COLUMN IF NOT EXISTS
                            network_company JSONB,

                        ADD COLUMN IF NOT EXISTS
                            network_source JSONB,

                        ADD COLUMN IF NOT EXISTS
                            station_uid TEXT,

                        ADD COLUMN IF NOT EXISTS
                            provider_last_updated TEXT,

                        ADD COLUMN IF NOT EXISTS
                            renting BIGINT,

                        ADD COLUMN IF NOT EXISTS
                            returning_allowed BIGINT,

                        ADD COLUMN IF NOT EXISTS
                            slots BIGINT,

                        ADD COLUMN IF NOT EXISTS
                            virtual BOOLEAN,

                        ADD COLUMN IF NOT EXISTS
                            installed BOOLEAN,

                        ADD COLUMN IF NOT EXISTS
                            locked BOOLEAN,

                        ADD COLUMN IF NOT EXISTS
                            status TEXT,

                        ADD COLUMN IF NOT EXISTS
                            ebikes BIGINT,

                        ADD COLUMN IF NOT EXISTS
                            has_ebikes BOOLEAN,

                        ADD COLUMN IF NOT EXISTS
                            normal_bikes BIGINT,

                        ADD COLUMN IF NOT EXISTS
                            address TEXT,

                        ADD COLUMN IF NOT EXISTS
                            payment_terminal BOOLEAN,

                        ADD COLUMN IF NOT EXISTS
                            payment JSONB,

                        ADD COLUMN IF NOT EXISTS
                            raw_extra JSONB,

                        ADD COLUMN IF NOT EXISTS
                            raw_station JSONB,

                        ADD COLUMN IF NOT EXISTS
                            source_url TEXT,

                        ADD COLUMN IF NOT EXISTS
                            http_status_code INTEGER,

                        ADD COLUMN IF NOT EXISTS
                            snapshot_id TEXT,

                        ADD COLUMN IF NOT EXISTS
                            raw_file_path TEXT;
                    """)
                )

        # -------------------------------------------------
        # 7. Guardar snapshot en Bronze
        # -------------------------------------------------
        df.to_sql(
            "citybikes_stations",
            engine,
            schema="bronze",
            if_exists="append",
            index=False,

            # Fuerza estas columnas a JSONB
            dtype={
                "network_company": JSONB,
                "network_source": JSONB,
                "payment": JSONB,
                "raw_extra": JSONB,
                "raw_station": JSONB,
            },
        )

        print(
            f"OK: {len(df)} filas agregadas a "
            "bronze.citybikes_stations"
        )

    ingest_citybikes()


citybikes_bronze()