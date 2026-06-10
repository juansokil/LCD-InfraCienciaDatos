"""
DAG Silver: Estandarización y Limpieza de tablas en Bronze
 
Pipeline:
bronze.networks    -> Contrato -> silver.networks
bronze.stations    -> ''       -> silver.stations
bronze.stations    -> ''       -> silver.station_availability
bronze.snapshots   -> ''       -> silver.snapshots

"""
 
from airflow.sdk import dag, task, get_current_context
from datetime import datetime, timedelta
import sqlalchemy
import yaml
import os
 
# =====================================================
# CONTRATO RUTA
# =====================================================
 
# CONTRACT_PATH = "/opt/airflow/data/contracts/silver_contracts.yaml"
 
CONTRACT_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__),
    "..", "..",
    "data",
    "contracts",
    "silver_contracts.yaml"
))

def get_engine():
    DB_URI = (
        f"postgresql+psycopg2://"
        f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
        f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
        f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
        f"{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
    )
    return sqlalchemy.create_engine(DB_URI)
 
# =====================================================
# CONTRATO
# =====================================================
 
def load_contract():
    with open(CONTRACT_PATH, "r") as f:
        return yaml.safe_load(f)
 
def build_create_sql(schema, table, columns):
    col_defs = ",\n    ".join(
        f'"{c["name"]}" {c["type"].upper()}'
        for c in columns
    )
    return f"""
        CREATE TABLE IF NOT EXISTS "{schema}"."{table}" (
            {col_defs}
        );
    """
 
def build_add_column_sql(schema, table, col):
    return f"""
        ALTER TABLE "{schema}"."{table}"
        ADD COLUMN IF NOT EXISTS "{col["name"]}" {col["type"].upper()};
    """

# ======================================================
# IDEMPOTENCIA
# ======================================================

def build_delete_sql(schema, table, partition_col):
    return f"""
        DELETE FROM "{schema}"."{table}"
        WHERE "{partition_col}" = %s;
    """
 
def build_insert_sql(schema, table, source_table, columns, ts, ds):
    col_names = ", ".join(f'"{c["name"]}"' for c in columns)
 
    select_parts = []
    for c in columns:
        if c["name"] == "ts":
            select_parts.append(f"'{ts}' AS ts")
        elif c["name"] == "ds":
            select_parts.append(f"'{ds}' AS ds")
        elif "cast" in c:
            select_parts.append(f'{c["cast"]} AS "{c["name"]}"')
        else:
            select_parts.append(f'"{c["name"]}"')
 
    select_clause = ",\n        ".join(select_parts)
    source_filter = f"""
        WHERE ts = (
            SELECT MAX(ts)
            FROM {source_table}
            WHERE ts <= '{ts}'
        )
    """
 
    return f"""
        INSERT INTO "{schema}"."{table}"
        ({col_names})
        SELECT
            {select_clause}
        FROM {source_table}
        {source_filter};
    """
 

 
@dag(
    dag_id="silver_citybikes",
    start_date=datetime(2024, 1, 1),
    schedule="*/5 * * * *",
    catchup=False,
    is_paused_upon_creation=False,
    default_args={
        "retries": 3,
        "retry_delay": timedelta(minutes=5),
        "retry_exponential_backoff": True,
    },
    tags=["silver", "citybikes", "ecobici-baires"]
)
def silver_citybikes_pipeline():
 
    @task
    def crear_schema():
        engine = get_engine()
        conn = engine.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute('CREATE SCHEMA IF NOT EXISTS "silver";')
            conn.commit()
            print("Schema silver OK")
        finally:
            conn.close()
            engine.dispose()
 
    @task
    def procesar_tabla(table_def: dict):
        ctx = get_current_context()
        ts = ctx["ts"]
        ds = ctx["ds"]
 
        schema   = table_def["schema"]
        table    = table_def["name"]
        columns  = table_def["columns"]
        src      = table_def["source"]["table"]
        part_col = table_def["idempotency"]["partition_col"]
 
        part_val = ds if part_col == "ds" else ts

        engine = get_engine()
        conn   = engine.raw_connection()
 
        try:
            cur = conn.cursor()
 
            # -----------------------------------------
            # CREATE TABLE
            # -----------------------------------------
            cur.execute(build_create_sql(schema, table, columns))
            conn.commit()
 
            # -----------------------------------------
            # SCHEMA EVOLUTION
            # -----------------------------------------
            for col in columns:
                cur.execute(build_add_column_sql(schema, table, col))
            conn.commit()
 
            cur.execute(
                f"SELECT MAX(ts) FROM {src} WHERE ts <= %s;",
                (ts,)
            )
            latest_bronze_ts = cur.fetchone()[0]
 
            if latest_bronze_ts is None:
                print(
                    f"silver.{table} SKIPPED — "
                    f"no bronze data available for ts <= {ts}"
                )
                return

            # -----------------------------------------
            # IDEMPOTENCIA
            # -----------------------------------------

            cur.execute(build_delete_sql(schema, table, part_col), (part_val,))           
            conn.commit()
 
            # -----------------------------------------
            # INSERT
            # -----------------------------------------
            insert_sql = build_insert_sql(schema, table, src, columns, ts, ds)
            cur.execute(insert_sql)
            conn.commit()
 
            row_count = cur.rowcount
            print(
                f"silver.{table} OK — "
                f"{row_count} rows inserted for {part_col}={part_val} "
                f"(from bronze ts={latest_bronze_ts})"
            )

 
        finally:
            conn.close()
            engine.dispose()
 
    # =====================================================
    # FLOW
    # =====================================================
 
    contract  = load_contract()
    schema_op = crear_schema()
 
    for table_def in contract["tables"]:
        task_op = procesar_tabla.override(
            task_id=f"procesar_{table_def['name']}"
        )(table_def)
        schema_op >> task_op
 
silver_citybikes_pipeline()
 