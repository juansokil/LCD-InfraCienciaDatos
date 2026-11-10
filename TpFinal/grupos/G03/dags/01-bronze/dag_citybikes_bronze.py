from airflow.sdk import dag, task
from datetime import datetime, timezone

import os
import requests
import pandas as pd
import sqlalchemy

from sqlalchemy.dialects.postgresql import JSONB


# =========================================================
# CONFIGURACIÓN
# =========================================================

API_URL = (
    "https://api.citybik.es/v2/networks/"
    "ecobici-buenos-aires"
)

RAW_BASE_DIR = (
    "/opt/airflow/data/raw/"
    "citybikes_ecobici_buenos_aires"
)


# =========================================================
# DAG
# =========================================================

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
        # 1. Consultar API CityBikes
        # -------------------------------------------------

        response = requests.get(
            API_URL,
            timeout=30,
        )

        response.raise_for_status()

        payload = response.json()

        network = payload["network"]

        stations = network["stations"]

        location = (
            network.get("location")
            or {}
        )

        print(
            f"Red: {network.get('name')}"
        )

        print(
            f"ID red: {network.get('id')}"
        )

        print(
            f"Ciudad: {location.get('city')}"
        )

        print(
            f"País: {location.get('country')}"
        )

        print(
            f"Estaciones recibidas: {len(stations)}"
        )

        # -------------------------------------------------
        # Inspección de campos extra disponibles
        # -------------------------------------------------

        extra_keys = sorted({
            key
            for station in stations
            for key in (
                station.get("extra")
                or {}
            ).keys()
        })

        print(
            f"Campos encontrados en extra: "
            f"{extra_keys}"
        )

        # -------------------------------------------------
        # 2. Guardar payload crudo en RAW
        # -------------------------------------------------

        now = datetime.now(
            timezone.utc
        )

        ds = now.strftime(
            "%Y-%m-%d"
        )

        timestamp_file = now.strftime(
            "%Y%m%dT%H%M%SZ"
        )

        raw_dir = (
            f"{RAW_BASE_DIR}/ds={ds}"
        )

        os.makedirs(
            raw_dir,
            exist_ok=True,
        )

        raw_file = (
            f"{raw_dir}/"
            f"ecobici_buenos_aires_"
            f"{timestamp_file}.json"
        )

        with open(
            raw_file,
            "wb",
        ) as f:

            f.write(
                response.content
            )

        print(
            f"RAW guardado en: "
            f"{raw_file}"
        )

        # -------------------------------------------------
        # Identificador común del snapshot
        # -------------------------------------------------

        snapshot_id = (
            timestamp_file
        )

        # -------------------------------------------------
        # 3. Construir dataset Bronze
        # -------------------------------------------------

        rows = []

        for station in stations:

            extra = (
                station.get("extra")
                or {}
            )

            uid = (
                extra.get("uid")
            )

            provider_last_updated = (
                extra.get(
                    "last_updated"
                )
            )

            post_code = (
                extra.get(
                    "post_code"
                )
            )

            # ---------------------------------------------
            # Normalización mínima Bronze
            # ---------------------------------------------
            #
            # CityBikes Buenos Aires devuelve renting y
            # returning como booleanos.
            #
            # Nuestro contrato Bronze/Silver utiliza:
            #
            # True  -> 1
            # False -> 0
            # None  -> NULL
            #
            # ---------------------------------------------

            renting = (
                int(
                    extra.get(
                        "renting"
                    )
                )
                if extra.get(
                    "renting"
                ) is not None
                else None
            )

            returning_allowed = (
                int(
                    extra.get(
                        "returning"
                    )
                )
                if extra.get(
                    "returning"
                ) is not None
                else None
            )

            rows.append({

                # =========================================
                # RED
                # =========================================

                "network_id":
                    network.get("id"),

                "network_name":
                    network.get("name"),

                "network_city":
                    location.get("city"),

                "network_country":
                    location.get("country"),

                "network_latitude":
                    location.get(
                        "latitude"
                    ),

                "network_longitude":
                    location.get(
                        "longitude"
                    ),

                "network_href":
                    network.get("href"),

                "network_gbfs_href":
                    network.get(
                        "gbfs_href"
                    ),

                # Puede ser lista u otra estructura.
                # Se conserva como JSONB.
                "network_company":
                    network.get(
                        "company"
                    ),

                # Metadata adicional de origen.
                "network_source":
                    network.get(
                        "source"
                    ),

                # =========================================
                # IDENTIFICACIÓN DE ESTACIÓN
                # =========================================

                "station_id":
                    station.get("id"),

                # UID propio del operador.
                "station_uid": (
                    str(uid)
                    if uid is not None
                    else None
                ),

                "station_name":
                    station.get("name"),

                # =========================================
                # GEOLOCALIZACIÓN
                # =========================================

                "latitude":
                    station.get(
                        "latitude"
                    ),

                "longitude":
                    station.get(
                        "longitude"
                    ),

                "altitude":
                    extra.get(
                        "altitude"
                    ),

                # =========================================
                # TIEMPO
                # =========================================

                "station_timestamp":
                    station.get(
                        "timestamp"
                    ),

                "provider_last_updated": (
                    str(
                        provider_last_updated
                    )
                    if provider_last_updated
                    is not None
                    else None
                ),

                # =========================================
                # DISPONIBILIDAD
                # =========================================

                "free_bikes":
                    station.get(
                        "free_bikes"
                    ),

                "empty_slots":
                    station.get(
                        "empty_slots"
                    ),

                # Capacidad nominal informada
                # por el proveedor.
                "slots":
                    extra.get(
                        "slots"
                    ),

                "normal_bikes":
                    extra.get(
                        "normal_bikes"
                    ),

                # Posibles bicicletas eléctricas.
                # Actualmente pueden venir NULL.
                "ebikes":
                    extra.get(
                        "ebikes"
                    ),

                "has_ebikes":
                    extra.get(
                        "has_ebikes"
                    ),

                # =========================================
                # ESTADO OPERATIVO
                # =========================================

                "renting":
                    renting,

                "returning_allowed":
                    returning_allowed,

                # Estos campos son booleanos reales
                # y se conservan como BOOLEAN.
                "virtual":
                    extra.get(
                        "virtual"
                    ),

                "installed":
                    extra.get(
                        "installed"
                    ),

                "locked":
                    extra.get(
                        "locked"
                    ),

                "status":
                    extra.get(
                        "status"
                    ),

                # =========================================
                # INFORMACIÓN DESCRIPTIVA
                # =========================================

                "address":
                    extra.get(
                        "address"
                    ),

                # Siempre se guarda como texto.
                # Hay códigos como C1056, 1111, etc.
                "post_code": (
                    str(post_code)
                    if post_code is not None
                    else None
                ),

                # =========================================
                # PAGO / ALQUILER
                # =========================================

                "payment_terminal":
                    extra.get(
                        "payment-terminal"
                    ),

                # Lista de medios de pago.
                "payment":
                    extra.get(
                        "payment"
                    ),

                # URLs específicas del operador.
                "rental_uris":
                    extra.get(
                        "rental_uris"
                    ),

                # =========================================
                # PRESERVACIÓN COMPLETA DEL ORIGEN
                # =========================================

                # Objeto extra completo.
                "raw_extra":
                    extra,

                # Estación completa tal como llega.
                "raw_station":
                    station,

                # =========================================
                # AUDITORÍA DE INGESTA
                # =========================================

                "source_url":
                    API_URL,

                "http_status_code":
                    response.status_code,

                "snapshot_id":
                    snapshot_id,

                "raw_file_path":
                    raw_file,

                "ingested_at":
                    now,
            })

        # -------------------------------------------------
        # DataFrame Bronze
        # -------------------------------------------------

        df = pd.DataFrame(
            rows
        )

        print(
            f"Columnas Bronze: "
            f"{list(df.columns)}"
        )

        print(
            f"Filas Bronze generadas: "
            f"{len(df)}"
        )

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
                    """
                    CREATE SCHEMA
                    IF NOT EXISTS bronze;
                    """
                )
            )

        # -------------------------------------------------
        # 6. Asegurar estructura de tabla Bronze
        # -------------------------------------------------

        inspector = (
            sqlalchemy.inspect(
                engine
            )
        )

        if inspector.has_table(
            "citybikes_stations",
            schema="bronze",
        ):

            with engine.begin() as conn:

                conn.execute(
                    sqlalchemy.text(
                        """
                        ALTER TABLE
                        bronze.citybikes_stations

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
                            post_code TEXT,

                        ADD COLUMN IF NOT EXISTS
                            altitude DOUBLE PRECISION,

                        ADD COLUMN IF NOT EXISTS
                            payment_terminal BOOLEAN,

                        ADD COLUMN IF NOT EXISTS
                            payment JSONB,

                        ADD COLUMN IF NOT EXISTS
                            rental_uris JSONB,

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
                        """
                    )
                )

        # -------------------------------------------------
        # 7. Guardar snapshot estructurado en Bronze
        # -------------------------------------------------

        df.to_sql(
            "citybikes_stations",
            engine,
            schema="bronze",
            if_exists="append",
            index=False,

            # ---------------------------------------------
            # Columnas que deben persistirse como JSONB
            # ---------------------------------------------
            dtype={
                "network_company":
                    JSONB,

                "network_source":
                    JSONB,

                "payment":
                    JSONB,

                "rental_uris":
                    JSONB,

                "raw_extra":
                    JSONB,

                "raw_station":
                    JSONB,
            },
        )

        # -------------------------------------------------
        # 8. Resumen de ejecución
        # -------------------------------------------------

        print(
            f"OK: {len(df)} filas "
            f"agregadas a "
            f"bronze.citybikes_stations"
        )

        print(
            f"Snapshot ID: "
            f"{snapshot_id}"
        )

        print(
            f"Red cargada: "
            f"{network.get('id')}"
        )

        print(
            f"Ciudad cargada: "
            f"{location.get('city')}"
        )

    ingest_citybikes()


citybikes_bronze()