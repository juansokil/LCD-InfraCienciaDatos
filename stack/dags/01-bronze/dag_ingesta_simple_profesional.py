
# ==========================================================
# DAG: Bronze ingest + Idempotencia por FILE HASH + Move files
# ==========================================================
# Cuándo usar este patrón:
# - Recibís múltiples archivos por día
# - El nombre del archivo puede repetirse o cambiar
# - Querés evitar duplicados incluso si el mismo contenido llega 2 veces
#
# Idea:
# - Calculamos un hash del archivo (sha256)
# - Antes de insertar, borramos cualquier carga previa con ese mismo file_hash
# - Insertamos filas con metadata: ds, source_file, file_hash
# - Movemos el archivo a /processed/ds=YYYY-MM-DD/
#
# Nota: en Bronze dejamos columnas del CSV como TEXT (simple) y tipamos en Silver.




from airflow.decorators import dag, task
from airflow.operators.python import get_current_context
from datetime import datetime

import pandas as pd
import sqlalchemy
import os
import shutil
import hashlib


def sha256_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    """
    Calcula SHA256 de un archivo leyendo por chunks (no carga todo en RAM).
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


@dag(
    dag_id="ingesta_simple_profesional",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["bronze"],
)
def ingesta_simple_profesional():

    @task
    def ingesta_profesional():
        # -----------------------------
        # 1) Paths
        # -----------------------------
        landing_path = "/opt/airflow/data/landing"
        processed_path = "/opt/airflow/data/processed"

        if not os.path.exists(landing_path):
            return

        os.makedirs(processed_path, exist_ok=True)

        files = sorted([f for f in os.listdir(landing_path) if f.endswith(".csv")])
        if not files:
            return

        # -----------------------------
        # 2) Determinismo: ds Airflow
        # -----------------------------
        ctx = get_current_context()
        ds = ctx["ds"]  # 'YYYY-MM-DD'

        # -----------------------------
        # 3) DB: Postgres (schema bronze)
        # -----------------------------
        engine = sqlalchemy.create_engine(
            f"postgresql+psycopg2://{os.getenv('SOURCE_DB_USER')}:{os.getenv('SOURCE_DB_PASS')}"
            f"@{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432"
            f"/{os.getenv('SOURCE_DB_NAME')}"
        )

        schema = "bronze"
        table = "ventas_simple"
        fq_table = f'"{schema}"."{table}"'

        conn = engine.raw_connection()
        try:
            cur = conn.cursor()

            # 3a) Asegurar schema + tabla base (metadata mínima)
            cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}";')
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {fq_table} (
                    ds          text,
                    source_file text,
                    file_hash   text
                );
            """)
            conn.commit()

            # 4) Procesar archivo por archivo (unidad de idempotencia = file_hash)
            for f in files:
                file_path = os.path.join(landing_path, f)

                # 4a) Hash del archivo: identifica el CONTENIDO, no el nombre
                file_hash = sha256_file(file_path)

                # 4b) Leemos CSV y normalizamos columnas
                df = pd.read_csv(file_path)
                df.columns = [c.strip().replace(" ", "_") for c in df.columns]

                # 4c) Metadata Bronze
                df["ds"] = ds
                df["source_file"] = f
                df["file_hash"] = file_hash

                # 4d) Evolución de esquema: agregar columnas del CSV como TEXT si no existen
                for col in df.columns:
                    if col in ("ds", "source_file", "file_hash"):
                        continue
                    cur.execute(f'ALTER TABLE {fq_table} ADD COLUMN IF NOT EXISTS "{col}" text;')
                conn.commit()

                # 4e) Idempotencia por file_hash:
                #     Si el mismo contenido llega 2 veces, lo reemplazamos (no duplicamos).
                cur.execute(f"DELETE FROM {fq_table} WHERE file_hash = %s;", (file_hash,))
                conn.commit()

                # 4f) Insert (append seguro tras el delete)
                insert_cols = list(df.columns)
                cols_sql = ", ".join([f'"{c}"' for c in insert_cols])
                placeholders = ", ".join(["%s"] * len(insert_cols))

                insert_sql = f"""
                    INSERT INTO {fq_table} ({cols_sql})
                    VALUES ({placeholders});
                """

                df = df.where(pd.notnull(df), None)
                rows = [tuple(row) for row in df[insert_cols].to_numpy()]

                cur.executemany(insert_sql, rows)
                conn.commit()

                # 4g) Move a processed (para evitar reprocesar en la próxima corrida)
                #     Guardamos en subcarpeta ds=... para trazabilidad.
                ds_dir = os.path.join(processed_path, f"ds={ds}")
                os.makedirs(ds_dir, exist_ok=True)

                safe_original = f.replace(" ", "_")
                new_name = f"{file_hash}__{safe_original}"
                shutil.move(file_path, os.path.join(ds_dir, new_name))

        finally:
            conn.close()

    ingesta_profesional()


ingesta_simple_profesional()
