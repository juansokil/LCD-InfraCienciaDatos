
"""
DAG Bronze: ingesta multi-archivo con DYNAMIC TASK MAPPING (clase03).

Diferencia con `bronze_02_multiple.py`:
- En vez de un for-loop dentro de UNA task, expandimos N tasks
  (una por archivo) usando `.expand()`.
- Cada archivo es una corrida independiente:
    * Si uno falla, los otros NO se abortan.
    * En Airflow UI ves N cuadraditos en Grid View (uno por archivo).
    * Airflow puede paralelizarlos segun los slots disponibles.

Pipeline:
    listar_archivos()  ->  list[str] de paths del landing
            |
            v
    procesar_archivo.expand(filepath=...)  ->  N tasks paralelas
            |
            +-- OK   -> bronze.ventas_dynamic + processed/
            +-- FAIL -> quarantine/ + .error.json
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime

import pandas as pd
import sqlalchemy
from airflow.decorators import dag, task
from airflow.operators.python import get_current_context


BASE_DIR = "/opt/airflow/data"
LANDING = f"{BASE_DIR}/landing"
PROCESSED = f"{BASE_DIR}/processed"
QUARANTINE = f"{BASE_DIR}/quarantine"

for d in [LANDING, PROCESSED, QUARANTINE]:
    os.makedirs(d, exist_ok=True)


# Helpers (copia de bronze_02_multiple.py para que el DAG sea autocontenido)
def sha256_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def load_as_dataframe(filepath: str) -> tuple[pd.DataFrame, str]:
    name = os.path.basename(filepath).lower()
    if name.endswith(".csv"):
        return pd.read_csv(filepath), "csv"
    if name.endswith(".json"):
        with open(filepath, "r", encoding="utf-8") as jf:
            obj = json.load(jf)
        if isinstance(obj, list):
            return pd.DataFrame(obj), "json"
        if isinstance(obj, dict) and "data" in obj and isinstance(obj["data"], list):
            return pd.DataFrame(obj["data"]), "json"
        raise ValueError("JSON no es lista de objetos ni dict con 'data'")
    if name.endswith(".jsonl") or name.endswith(".ndjson"):
        return pd.read_json(filepath, lines=True), "jsonl"
    if name.endswith(".parquet"):
        return pd.read_parquet(filepath), "parquet"
    raise ValueError("Formato desconocido")


@dag(
    dag_id="bronze_03_dynamic",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["bronze"],
    doc_md="Ingesta Bronze multi-archivo usando .expand() — una task por archivo del landing.",
)
def bronze_03_dynamic():

    @task
    def listar_archivos() -> list[str]:
        """
        Devuelve la lista de filepaths del landing que vamos a procesar.
        Esta lista es lo que `.expand()` consume para crear N tasks.
        Filtramos por prefijo 'ventas' para no pisar otros datasets.
        """
        archivos = [
            os.path.join(LANDING, f)
            for f in sorted(os.listdir(LANDING))
            if os.path.isfile(os.path.join(LANDING, f)) and f.lower().startswith("ventas")
        ]
        print(f"📂 {len(archivos)} archivos detectados en landing: {[os.path.basename(p) for p in archivos]}")
        return archivos

    @task
    def procesar_archivo(filepath: str) -> str:
        """
        Procesa UN archivo: hash + load + insert + move.
        Esta funcion se ejecuta N veces (una por archivo) gracias a .expand().
        """
        ctx = get_current_context()
        ds = ctx["ds"]

        f = os.path.basename(filepath)
        file_hash = sha256_file(filepath)
        _, ext = os.path.splitext(f)
        ext = ext.lower()

        engine = sqlalchemy.create_engine(
            f"postgresql+psycopg2://{os.getenv('SOURCE_DB_USER','admin')}:"
            f"{os.getenv('SOURCE_DB_PASS','admin')}@"
            f"{os.getenv('SOURCE_DB_HOST','data_warehouse')}:5432/"
            f"{os.getenv('SOURCE_DB_NAME','InfraCienciaDatos')}"
        )
        schema_db = "bronze"
        table = "ventas_dynamic"
        fq_table = f'"{schema_db}"."{table}"'

        conn = engine.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_db}";')
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {fq_table} (
                    ds          text,
                    source_file text,
                    file_hash   text,
                    file_format text
                );
            """)
            conn.commit()

            try:
                df, fmt = load_as_dataframe(filepath)
                df.columns = [c.strip().replace(" ", "_") for c in df.columns]
                df["ds"] = ds
                df["source_file"] = f
                df["file_hash"] = file_hash
                df["file_format"] = fmt

                # Evolucion suave: agregar columnas del payload como TEXT
                for col in df.columns:
                    if col in ("ds", "source_file", "file_hash", "file_format"):
                        continue
                    cur.execute(
                        f'ALTER TABLE {fq_table} ADD COLUMN IF NOT EXISTS "{col}" text;'
                    )
                conn.commit()

                # Idempotencia por hash
                cur.execute(f"DELETE FROM {fq_table} WHERE file_hash = %s;", (file_hash,))
                conn.commit()

                insert_cols = list(df.columns)
                cols_sql = ", ".join([f'"{c}"' for c in insert_cols])
                placeholders = ", ".join(["%s"] * len(insert_cols))
                insert_sql = f"INSERT INTO {fq_table} ({cols_sql}) VALUES ({placeholders});"

                df = df.where(pd.notnull(df), None)
                rows = [tuple(row) for row in df[insert_cols].to_numpy()]
                cur.executemany(insert_sql, rows)
                conn.commit()

                # Move a processed
                ds_dir = os.path.join(PROCESSED, f"ds={ds}")
                os.makedirs(ds_dir, exist_ok=True)
                shutil.move(filepath, os.path.join(ds_dir, f"{file_hash}{ext}"))
                msg = f"[ok] {f} -> bronze.{table} ({len(rows)} filas)"
                print(msg)
                return msg

            except Exception as e:
                # Quarantine: este archivo va a quarantine, pero las OTRAS tasks
                # del .expand() siguen corriendo (este es el valor de aislamiento).
                ds_dir = os.path.join(QUARANTINE, f"ds={ds}")
                os.makedirs(ds_dir, exist_ok=True)
                quarantined_path = os.path.join(ds_dir, f"{file_hash}{ext}" if ext else file_hash)
                shutil.move(filepath, quarantined_path)
                err_manifest = {
                    "original_name": f,
                    "file_hash": file_hash,
                    "ds": ds,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                }
                with open(quarantined_path + ".error.json", "w", encoding="utf-8") as ef:
                    json.dump(err_manifest, ef, ensure_ascii=False, indent=2)
                # Re-lanzamos para que la TASK falle (no el DAG entero)
                raise

        finally:
            conn.close()

    # La magia: una task por archivo, con grafo expandido en runtime
    procesar_archivo.expand(filepath=listar_archivos())


bronze_03_dynamic()
