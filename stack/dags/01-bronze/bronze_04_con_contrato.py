
"""
DAG Bronze: ingesta validada por DATA CONTRACT (clase03).

Pipeline:
    landing/  -->  validar contrato (forma)  -->  bronze.ventas_contrato
                                              \\->  quarantine/ + .error.json

Diferencia con `bronze_02_multiple.py`:
- ANTES de cargar el archivo, valida la FORMA contra `ventas.yaml`
  (extension, encoding, delimiter, header, columnas requeridas).
- El motivo del rechazo se serializa en el `.error.json` con la
  seccion+regla del contrato violada (no solo el traceback de Python).

Lo que SIGUE igual:
- SHA256 hash para idempotencia.
- Move a processed/quarantine bajo `ds=YYYY-MM-DD/`.
- Tabla bronze como TEXT (los tipos se aplican en Silver / clase04).

Lo que NO valida este DAG (clase04 lo hace en Silver):
- tipos de cada columna fila por fila
- allowed_values, ranges, regex
- unique, not_null por fila
- evolution_policy.allow_type_changes
- SCD
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from datetime import datetime

import pandas as pd
import sqlalchemy
from airflow.decorators import dag, task
from airflow.operators.python import get_current_context

# Hacemos visible el paquete `common` (esta dos niveles arriba)
sys.path.append("/opt/airflow/dags")
from common.contracts import ContractViolation, load_contract, validate_file_shape  # noqa: E402


BASE_DIR = "/opt/airflow/data"
LANDING = f"{BASE_DIR}/landing"
PROCESSED = f"{BASE_DIR}/processed"
QUARANTINE = f"{BASE_DIR}/quarantine"
CONTRACT_PATH = f"{BASE_DIR}/contracts/ventas.yaml"

for d in [LANDING, PROCESSED, QUARANTINE]:
    os.makedirs(d, exist_ok=True)


def sha256_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    """Hash del archivo para idempotencia por contenido.

    Reusa el mismo patron que `bronze_01_simple.py` y
    `bronze_02_multiple.py`.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _quarantine(filepath: str, file_hash: str, ds: str, error_payload: dict) -> None:
    """Mueve el archivo a quarantine y deja un manifest .error.json al lado."""
    ext = os.path.splitext(filepath)[1].lower()
    ds_dir = os.path.join(QUARANTINE, f"ds={ds}")
    os.makedirs(ds_dir, exist_ok=True)

    new_name = f"{file_hash}{ext}" if ext else file_hash
    quarantined_path = os.path.join(ds_dir, new_name)
    shutil.move(filepath, quarantined_path)

    with open(quarantined_path + ".error.json", "w", encoding="utf-8") as ef:
        json.dump(error_payload, ef, ensure_ascii=False, indent=2)


@dag(
    dag_id="bronze_04_con_contrato",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["bronze"],
)
def bronze_04_con_contrato():

    @task
    def procesar_con_contrato():
        ctx = get_current_context()
        ds = ctx["ds"]

        # 1) Cargar contrato (una sola vez)
        contract = load_contract(CONTRACT_PATH)
        dataset = contract["dataset"]

        # 2) DB destino (bronze como TEXT, igual que los DAGs previos)
        engine = sqlalchemy.create_engine(
            f"postgresql+psycopg2://{os.getenv('SOURCE_DB_USER','admin')}:"
            f"{os.getenv('SOURCE_DB_PASS','admin')}@"
            f"{os.getenv('SOURCE_DB_HOST','data_warehouse')}:5432/"
            f"{os.getenv('SOURCE_DB_NAME','InfraCienciaDatos')}"
        )
        schema_db = "bronze"
        table = "ventas_contrato"
        fq_table = f'"{schema_db}"."{table}"'

        conn = engine.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_db}";')
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {fq_table} (
                    ds              text,
                    source_file     text,
                    file_hash       text,
                    contract_version text
                );
            """)
            conn.commit()

            # 3) Procesar cada archivo del landing que aparente ser de este dataset
            #    (filtramos por prefijo del dataset; el resto lo ignora este DAG)
            for f in sorted(os.listdir(LANDING)):
                filepath = os.path.join(LANDING, f)
                if not os.path.isfile(filepath):
                    continue
                if not f.lower().startswith(dataset):
                    continue

                file_hash = sha256_file(filepath)

                # 3a) VALIDAR CONTRATO (forma) ANTES de leer el contenido
                try:
                    validate_file_shape(filepath, contract)
                except ContractViolation as cv:
                    print(f"[contract] {f} -> rechazado por {cv.section}.{cv.rule}: {cv.message}")
                    _quarantine(
                        filepath,
                        file_hash,
                        ds,
                        {
                            "original_name": f,
                            "file_hash": file_hash,
                            "ds": ds,
                            "dataset": dataset,
                            "contract_version": contract.get("version"),
                            "contract_violated": cv.section,
                            "rule": cv.rule,
                            "details": cv.details,
                        },
                    )
                    continue

                # 3b) Pasa el contrato -> leer y cargar a Bronze
                try:
                    df = pd.read_csv(
                        filepath,
                        sep=contract["format"]["delimiter"],
                        encoding=contract["format"]["encoding"],
                    )
                    df.columns = [c.strip().replace(" ", "_") for c in df.columns]

                    # Metadata Bronze
                    df["ds"] = ds
                    df["source_file"] = f
                    df["file_hash"] = file_hash
                    df["contract_version"] = str(contract.get("version"))

                    # Evolucion suave: agregamos columnas del payload como TEXT
                    for col in df.columns:
                        if col in ("ds", "source_file", "file_hash", "contract_version"):
                            continue
                        cur.execute(
                            f'ALTER TABLE {fq_table} ADD COLUMN IF NOT EXISTS "{col}" text;'
                        )
                    conn.commit()

                    # Idempotencia por file_hash
                    cur.execute(f"DELETE FROM {fq_table} WHERE file_hash = %s;", (file_hash,))
                    conn.commit()

                    # Insert
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
                    ext = os.path.splitext(f)[1].lower()
                    new_name = f"{file_hash}{ext}"
                    shutil.move(filepath, os.path.join(ds_dir, new_name))
                    print(f"[ok] {f} -> bronze.{table} ({len(rows)} filas)")

                except Exception as e:
                    # Falla post-contrato (parseo, DB, ...) -> quarantine generica
                    _quarantine(
                        filepath,
                        file_hash,
                        ds,
                        {
                            "original_name": f,
                            "file_hash": file_hash,
                            "ds": ds,
                            "dataset": dataset,
                            "contract_version": contract.get("version"),
                            "contract_violated": "runtime",
                            "rule": "post_contract_load_error",
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                        },
                    )
                    print(f"[runtime] {f} -> quarantine ({type(e).__name__}): {e}")

        finally:
            conn.close()

    procesar_con_contrato()


bronze_04_con_contrato()
