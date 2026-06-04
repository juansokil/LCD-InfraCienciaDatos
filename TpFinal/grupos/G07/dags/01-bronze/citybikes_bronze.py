"""
DAG Bronze: Ingesta de API CityBikes (Ecobici Buenos Aires)

Pipeline:
API -> Landing -> Metadata -> Idempotencia -> Bronze(Postgres) -> Processed
"""

from airflow.sdk import dag, task
from airflow.operators.python import get_current_context
from datetime import datetime, UTC
import requests
import pandas as pd
import sqlalchemy
import os
import shutil
import json

# =====================================================
# DIRECTORIOS
# =====================================================

BASE_DIR = "/opt/airflow/data"
LANDING = f"{BASE_DIR}/landing"
PROCESSED = f"{BASE_DIR}/processed"

for d in [LANDING, PROCESSED]:
    os.makedirs(d, exist_ok=True)

# =====================================================
# DAG
# =====================================================

@dag(
    dag_id="bronze_citybikes_api",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["bronze", "citybikes", "ecobici"]
)
def bronze_citybikes_pipeline():

    @task
    def extraer_y_cargar_bronze():

        ctx = get_current_context()
        ds = ctx["ds"]

        # =================================================
        # EXTRACCIÓN
        # =================================================

        url = "http://api.citybik.es/v2/networks/ecobici"

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            raw_data = response.json()
        except requests.RequestException as e:
            raise Exception(f"Error consultando API CityBikes: {e}")

        # =================================================
        # LANDING
        # =================================================

        filename = "ecobici_stations.json"

        landing_path = os.path.join(
            LANDING,
            filename
        )

        with open(
            landing_path,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                raw_data,
                f,
                ensure_ascii=False,
                indent=2
            )

        # =================================================
        # NORMALIZACIÓN BRONZE
        # =================================================

        stations = raw_data["network"]["stations"]

        df = pd.DataFrame(stations)

        # convertir estructuras complejas a JSON
        for col in df.columns:
            df[col] = df[col].apply(
                lambda x: json.dumps(x)
                if isinstance(x, (dict, list))
                else x
            )

        df.columns = [
            c.strip().replace(" ", "_")
            for c in df.columns
        ]

        # =================================================
        # METADATA
        # =================================================

        df["ds"] = ds
        df["source_url"] = url
        df["ingested_at"] = datetime.now(UTC).isoformat()

        # =================================================
        # POSTGRES
        # =================================================

        DB_URI = (
            f"postgresql+psycopg2://"
            f"{os.getenv('SOURCE_DB_USER','admin')}:"
            f"{os.getenv('SOURCE_DB_PASS','admin')}@"
            f"{os.getenv('SOURCE_DB_HOST','data_warehouse')}:5432/"
            f"{os.getenv('SOURCE_DB_NAME','InfraCienciaDatos')}"
        )

        engine = sqlalchemy.create_engine(DB_URI)

        schema_db = "bronze"
        table = "ecobici_stations"

        fq_table = f'"{schema_db}"."{table}"'

        conn = engine.raw_connection()

        try:

            cur = conn.cursor()

            # =============================================
            # CREAR SCHEMA
            # =============================================

            cur.execute(
                f'CREATE SCHEMA IF NOT EXISTS "{schema_db}";'
            )

            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {fq_table} (
                    ds text,
                    source_url text,
                    ingested_at text
                );
                """
            )

            conn.commit()

            # =============================================
            # EVOLUCIÓN DE ESQUEMA
            # =============================================

            for col in df.columns:

                if col in (
                    "ds",
                    "source_url",
                    "ingested_at"
                ):
                    continue

                cur.execute(
                    f'''
                    ALTER TABLE {fq_table}
                    ADD COLUMN IF NOT EXISTS "{col}" text;
                    '''
                )

            conn.commit()

            # =============================================
            # IDEMPOTENCIA
            # =============================================

            cur.execute(
                f"DELETE FROM {fq_table} WHERE ds = %s;",
                (ds,)
            )

            conn.commit()

            # =============================================
            # INSERT
            # =============================================

            insert_cols = list(df.columns)

            cols_sql = ", ".join(
                [f'"{c}"' for c in insert_cols]
            )

            placeholders = ", ".join(
                ["%s"] * len(insert_cols)
            )

            insert_sql = f"""
                INSERT INTO {fq_table}
                ({cols_sql})
                VALUES ({placeholders});
            """

            df = df.where(
                pd.notnull(df),
                None
            )

            rows = [
                tuple(row)
                for row in df[insert_cols].to_numpy()
            ]

            cur.executemany(
                insert_sql,
                rows
            )

            conn.commit()

            # =============================================
            # PROCESSED
            # =============================================

            ds_dir = os.path.join(
                PROCESSED,
                f"ds={ds}"
            )

            os.makedirs(
                ds_dir,
                exist_ok=True
            )

            timestamp_str = datetime.now().strftime(
                "%H%M%S"
            )

            final_filename = (
                f"{timestamp_str}__{filename}"
            )

            shutil.move(
                landing_path,
                os.path.join(
                    ds_dir,
                    final_filename
                )
            )

            print(
                f"Ingesta exitosa. "
                f"Se guardaron {len(rows)} estaciones "
                f"en bronze.ecobici_stations"
            )

        finally:
            conn.close()
            engine.dispose()

    extraer_y_cargar_bronze()

dag_instance = bronze_citybikes_pipeline()