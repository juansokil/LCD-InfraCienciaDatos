
# =========================
# DAG: Ingesta Bronze (ELT)
# =========================
# Objetivo para clase:
# - Leer CSVs desde una landing zone
# - Cargar los registros en Postgres (capa Bronze)
# - Crear la tabla si no existe
# - Luego siempre APPEND de casos nuevos
#
# NOTA IMPORTANTE:
# - Evitamos pandas.to_sql porque en algunos entornos (Airflow 3 + pandas + SQLAlchemy 2)
#   puede intentar ejecutar SQL de SQLite (sqlite_master) contra Postgres.
# - En su lugar, hacemos inserts con DBAPI (cursor.execute / executemany).




from airflow.decorators import dag, task
from airflow.operators.python import get_current_context
from datetime import datetime

import pandas as pd
import sqlalchemy
import os


@dag(
    dag_id="ingesta_simple",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["bronze"],
)
def ingesta_simple():

    @task
    def ingesta_basica():
        """
        Ingesta Bronze a Postgres usando schema 'bronze' y tabla 'ventas_simple'.

        - Crea el schema si no existe
        - Crea la tabla base (metadata) si no existe
        - Si el CSV trae columnas nuevas, las agrega (ALTER TABLE ... ADD COLUMN IF NOT EXISTS)
        - Luego hace APPEND de filas nuevas
        """

        source_path = "/opt/airflow/data/landing"
        if not os.path.exists(source_path):
            return

        files = sorted([f for f in os.listdir(source_path) if f.endswith(".csv")])
        if not files:
            return

        # Determinismo: fecha lógica del DAG
        ctx = get_current_context()
        ds = ctx["ds"]

        # Conexión a Postgres (via env vars del .env)
        engine = sqlalchemy.create_engine(
            f"postgresql+psycopg2://{os.getenv('SOURCE_DB_USER')}:{os.getenv('SOURCE_DB_PASS')}"
            f"@{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432"
            f"/{os.getenv('SOURCE_DB_NAME')}"
        )

        schema = "bronze"
        table = "ventas_simple"
        fq_table = f'"{schema}"."{table}"'  # fully-qualified table name con comillas

        conn = engine.raw_connection()
        try:
            cur = conn.cursor()

            # 1) Asegurar schema
            cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}";')

            # 2) Crear tabla base si no existe (solo metadata)
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {fq_table} (
                    ds          text,
                    source_file text
                );
            """)
            conn.commit()

            # 3) Por cada CSV: asegurar columnas y luego insertar
            for f in files:
                df = pd.read_csv(os.path.join(source_path, f))

                # Normalizamos nombres de columnas para evitar espacios raros
                df.columns = [c.strip().replace(" ", "_") for c in df.columns]

                # Metadata mínima
                df["ds"] = ds
                df["source_file"] = f

                # 3a) Evolución de esquema: agregar columnas nuevas como TEXT
                for col in df.columns:
                    if col in ("ds", "source_file"):
                        continue
                    cur.execute(f'ALTER TABLE {fq_table} ADD COLUMN IF NOT EXISTS "{col}" text;')
                conn.commit()

                # 3b) Insert APPEND
                insert_cols = list(df.columns)
                cols_sql = ", ".join([f'"{c}"' for c in insert_cols])
                placeholders = ", ".join(["%s"] * len(insert_cols))

                insert_sql = f"""
                    INSERT INTO {fq_table} ({cols_sql})
                    VALUES ({placeholders});
                """

                # NaN -> None para DB
                df = df.where(pd.notnull(df), None)
                rows = [tuple(row) for row in df[insert_cols].to_numpy()]

                cur.executemany(insert_sql, rows)
                conn.commit()

        finally:
            conn.close()

    ingesta_basica()


ingesta_simple()
