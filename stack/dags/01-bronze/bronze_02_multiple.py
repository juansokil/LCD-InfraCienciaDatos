

from airflow.decorators import dag, task
from airflow.operators.python import get_current_context
from datetime import datetime

import pandas as pd
import sqlalchemy
import os
import shutil
import json
import hashlib


BASE_DIR = "/opt/airflow/data"
LANDING = f"{BASE_DIR}/landing"
PROCESSED = f"{BASE_DIR}/processed"
QUARANTINE = f"{BASE_DIR}/quarantine"

for d in [LANDING, PROCESSED, QUARANTINE]:
    os.makedirs(d, exist_ok=True)


def sha256_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    """Hash del archivo para idempotencia por contenido."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def load_as_dataframe(filepath: str) -> tuple[pd.DataFrame, str]:
    """
    Detecta formato por extensión y devuelve (df, fmt).
    Si el formato no está soportado o falta dependencia, lanza excepción.
    """
    name = os.path.basename(filepath).lower()

    if name.endswith(".csv"):
        return pd.read_csv(filepath), "csv"

    if name.endswith(".json"):
        # Soporta: lista de objetos [{...},{...}] o dict {"data":[...]}
        with open(filepath, "r", encoding="utf-8") as jf:
            obj = json.load(jf)
        if isinstance(obj, list):
            return pd.DataFrame(obj), "json"
        if isinstance(obj, dict) and "data" in obj and isinstance(obj["data"], list):
            return pd.DataFrame(obj["data"]), "json"
        raise ValueError("JSON no es lista de objetos ni dict con clave 'data' list")

    if name.endswith(".jsonl") or name.endswith(".ndjson"):
        # JSON lines: un objeto por línea
        return pd.read_json(filepath, lines=True), "jsonl"

    if name.endswith(".parquet"):
        # requiere pyarrow o fastparquet
        return pd.read_parquet(filepath), "parquet"

    if name.endswith(".xlsx") or name.endswith(".xls"):
        # requiere openpyxl (xlsx) / xlrd (xls)
        return pd.read_excel(filepath), "excel"

    raise ValueError("Formato desconocido")


@dag(
    dag_id="bronze_02_multiple",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["bronze"],
)
def bronze_02_multiple():

    @task
    def procesar_inteligente():
        """
        Pipeline robusto (Bronze):
        - Detecta formato (csv/json/jsonl/parquet/excel)
        - Normaliza a DataFrame
        - Idempotencia por FILE HASH: borra lo previo con el mismo hash y re-inserta
        - Move: processed/quarantine renombrando por hash
        - Quarantine: guarda un .error.json con el motivo
        """

        ctx = get_current_context()
        ds = ctx["ds"]  # determinista

        engine = sqlalchemy.create_engine(
            f"postgresql+psycopg2://{os.getenv('SOURCE_DB_USER','admin')}:{os.getenv('SOURCE_DB_PASS','admin')}@{os.getenv('SOURCE_DB_HOST','data_warehouse')}:5432/{os.getenv('SOURCE_DB_NAME','InfraCienciaDatos')}"
        )

        schema = "bronze"
        table = "ventas_multiple" 
        fq_table = f'"{schema}"."{table}"'

        conn = engine.raw_connection()
        try:
            cur = conn.cursor()

            # Asegurar schema + tabla base (metadata)
            cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}";')
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {fq_table} (
                    ds          text,
                    source_file text,
                    file_hash   text,
                    file_format text
                );
            """)
            # Migración simple por si ya existía sin alguna columna
            cur.execute(f'ALTER TABLE {fq_table} ADD COLUMN IF NOT EXISTS ds text;')
            cur.execute(f'ALTER TABLE {fq_table} ADD COLUMN IF NOT EXISTS source_file text;')
            cur.execute(f'ALTER TABLE {fq_table} ADD COLUMN IF NOT EXISTS file_hash text;')
            cur.execute(f'ALTER TABLE {fq_table} ADD COLUMN IF NOT EXISTS file_format text;')
            conn.commit()

            # Procesar archivos del landing
            for f in sorted(os.listdir(LANDING)):
                filepath = os.path.join(LANDING, f)
                if not os.path.isfile(filepath):
                    continue

                file_hash = sha256_file(filepath)
                _, ext = os.path.splitext(f)
                ext = ext.lower()

                try:
                    # 1) Detectar y cargar DF
                    df, fmt = load_as_dataframe(filepath)

                    # 2) Normalizar columnas
                    df.columns = [c.strip().replace(" ", "_") for c in df.columns]

                    # 3) Metadata determinista
                    df["ds"] = ds
                    df["source_file"] = f
                    df["file_hash"] = file_hash
                    df["file_format"] = fmt

                    # 4) Evolución de esquema para columnas del payload (como TEXT)
                    for col in df.columns:
                        if col in ("ds", "source_file", "file_hash", "file_format"):
                            continue
                        cur.execute(f'ALTER TABLE {fq_table} ADD COLUMN IF NOT EXISTS "{col}" text;')
                    conn.commit()

                    # 5) Idempotencia por contenido: reemplazamos cualquier carga previa del mismo hash
                    cur.execute(f"DELETE FROM {fq_table} WHERE file_hash = %s;", (file_hash,))
                    conn.commit()

                    # 6) Insert en Postgres (sin pandas.to_sql)
                    insert_cols = list(df.columns)
                    cols_sql = ", ".join([f'"{c}"' for c in insert_cols])
                    placeholders = ", ".join(["%s"] * len(insert_cols))
                    insert_sql = f"INSERT INTO {fq_table} ({cols_sql}) VALUES ({placeholders});"

                    df = df.where(pd.notnull(df), None)
                    rows = [tuple(row) for row in df[insert_cols].to_numpy()]
                    cur.executemany(insert_sql, rows)
                    conn.commit()

                    # 7) Move a processed con nombre basado en hash
                    ds_dir = os.path.join(PROCESSED, f"ds={ds}")
                    os.makedirs(ds_dir, exist_ok=True)
                    new_name = f"{file_hash}{ext}"  # conserva extensión
                    shutil.move(filepath, os.path.join(ds_dir, new_name))

                except Exception as e:
                    # Cuarentena: movemos el archivo y guardamos un manifest de error
                    ds_dir = os.path.join(QUARANTINE, f"ds={ds}")
                    os.makedirs(ds_dir, exist_ok=True)

                    new_name = f"{file_hash}{ext}" if ext else file_hash
                    quarantined_path = os.path.join(ds_dir, new_name)

                    # movemos el archivo a cuarentena
                    shutil.move(filepath, quarantined_path)

                    # guardamos detalle del error (útil en debugging y observabilidad)
                    err_manifest = {
                        "original_name": f,
                        "file_hash": file_hash,
                        "ds": ds,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    }
                    with open(quarantined_path + ".error.json", "w", encoding="utf-8") as ef:
                        json.dump(err_manifest, ef, ensure_ascii=False, indent=2)

                    print(f"☣️ Cuarentena -> {f} ({type(e).__name__}): {e}")

        finally:
            conn.close()

    procesar_inteligente()


bronze_02_multiple()
