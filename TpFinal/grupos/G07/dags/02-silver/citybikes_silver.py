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
import pandas as pd
 
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

# =====================================================
# SOURCE FILTER HELPER
# =====================================================

def build_source_filter_sql(source_table, ts):
    return f"""
        src.ts = (
            SELECT MAX(ts)
            FROM {source_table}
            WHERE ts <= '{ts}'
        )
    """
 
def build_insert_sql(schema, table, source_table, columns, ts, ds, joins=None, quality_rules=None):
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
            select_parts.append(f'src."{c["name"]}"')

    select_clause = ",\n        ".join(select_parts)
    join_clause = "\n    ".join(joins or [])
    source_filter = build_source_filter_sql(source_table, ts)

    quarantine_conditions = [
        rule["quarantine_if"]
        for rule in (quality_rules or [])
        if isinstance(rule, dict) and "quarantine_if" in rule
    ]

    quarantine_filter = ""
    if quarantine_conditions:
        invalid_condition = " OR ".join(f"({cond})" for cond in quarantine_conditions)
        quarantine_filter = f"\n          AND NOT ({invalid_condition})"

    return f"""
        INSERT INTO "{schema}"."{table}"
        ({col_names})
        SELECT
            {select_clause}
        FROM {source_table} AS src
        {join_clause}
        WHERE {source_filter}
        {quarantine_filter};
    """

# =====================================================
# CUARENTENA
# =====================================================

def build_create_quarantine_sql(schema):
    return f"""
        CREATE TABLE IF NOT EXISTS "{schema}"."quarantine" (
            quarantine_id BIGSERIAL PRIMARY KEY,
            target_table TEXT NOT NULL,
            rule_name TEXT NOT NULL,
            rule_description TEXT,
            source_table TEXT NOT NULL,
            ds TEXT,
            ts TEXT,
            quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            record JSONB NOT NULL
        );
    """


def build_delete_quarantine_sql(schema, table, partition_col):
    return f"""
        DELETE FROM "{schema}"."quarantine"
        WHERE target_table = %s
          AND {partition_col} = %s;
    """


def build_quarantine_insert_sql(schema, table, source_table, ts, ds, joins, rule):
    join_clause = "\n    ".join(joins or [])
    source_filter = build_source_filter_sql(source_table, ts)
    rule_name = rule["name"]
    rule_description = rule.get("description", "")
    quarantine_if = rule["quarantine_if"]

    return f"""
        INSERT INTO "{schema}"."quarantine"
        (target_table, rule_name, rule_description, source_table, ds, ts, record)
        SELECT
            '{table}' AS target_table,
            '{rule_name}' AS rule_name,
            '{rule_description}' AS rule_description,
            '{source_table}' AS source_table,
            '{ds}' AS ds,
            '{ts}' AS ts,
            to_jsonb(src) AS record
        FROM {source_table} AS src
        {join_clause}
        WHERE {source_filter}
          AND ({quarantine_if});
    """

# =====================================================
# CONSTRAINTS FÍSICAS
# =====================================================

def constraint_name(prefix, table, columns):
    cols = "_".join(columns)
    return f"{prefix}_{table}_{cols}"


def quote_columns(columns):
    return ", ".join(f'"{c}"' for c in columns)


def split_schema_table(table_ref):
    schema, table = table_ref.split(".", 1)
    return schema, table


def build_add_pk_sql(schema, table, primary_key):
    pk_name = constraint_name("pk", table, primary_key)
    pk_cols = quote_columns(primary_key)

    return f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = '{pk_name}'
                  AND conrelid = '"{schema}"."{table}"'::regclass
            ) THEN
                ALTER TABLE "{schema}"."{table}"
                ADD CONSTRAINT "{pk_name}"
                PRIMARY KEY ({pk_cols});
            END IF;
        END $$;
    """


def build_add_fk_sql(schema, table, fk_def):
    columns = fk_def.get("columns") or [fk_def["column"]]
    references_table = fk_def.get("references_table")
    references_columns = fk_def.get("references_columns")

    if references_table is None:
        # Compatibilidad con el formato viejo:
        # references: silver.networks.network_id
        ref_parts = fk_def["references"].split(".")
        references_schema = ref_parts[0]
        references_table_name = ref_parts[1]
        references_columns = [ref_parts[2]]
    else:
        references_schema, references_table_name = split_schema_table(references_table)

    fk_name = constraint_name("fk", table, columns)
    fk_cols = quote_columns(columns)
    ref_cols = quote_columns(references_columns)

    return f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = '{fk_name}'
                  AND conrelid = '"{schema}"."{table}"'::regclass
            ) THEN
                ALTER TABLE "{schema}"."{table}"
                ADD CONSTRAINT "{fk_name}"
                FOREIGN KEY ({fk_cols})
                REFERENCES "{references_schema}"."{references_table_name}" ({ref_cols});
            END IF;
        END $$;
    """


def build_drop_constraint_sql(schema, table, constraint):
    return f"""
        ALTER TABLE IF EXISTS "{schema}"."{table}"
        DROP CONSTRAINT IF EXISTS "{constraint}";
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
    def cargar_station_barrios():
        engine = get_engine()
        BARRIOS_PATH = os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "..", "..",
            "data",
            "seeds",
            "station_barrios.csv"
        ))
        df = pd.read_csv(BARRIOS_PATH)
        df.to_sql(
            "station_barrios",
            engine,
            schema="silver",
            if_exists="replace",
            index=False
        )
        engine.dispose()

    @task
    def eliminar_constraints():
        contract = load_contract()
        engine = get_engine()
        conn = engine.raw_connection()

        try:
            cur = conn.cursor()

            # Primero se eliminan las FK, porque dependen de las PK.
            for table_def in contract["tables"]:
                schema = table_def["schema"]
                table = table_def["name"]

                for fk_def in table_def.get("foreign_keys", []):
                    columns = fk_def.get("columns") or [fk_def["column"]]
                    fk_name = constraint_name("fk", table, columns)
                    cur.execute(build_drop_constraint_sql(schema, table, fk_name))

            # Después se eliminan las PK.
            for table_def in contract["tables"]:
                schema = table_def["schema"]
                table = table_def["name"]
                primary_key = table_def.get("primary_key")

                if primary_key:
                    pk_name = constraint_name("pk", table, primary_key)
                    cur.execute(build_drop_constraint_sql(schema, table, pk_name))

            conn.commit()
            print("Constraints físicas eliminadas OK")

        finally:
            conn.close()
            engine.dispose()

    @task
    def aplicar_constraints():
        contract = load_contract()
        engine = get_engine()
        conn = engine.raw_connection()

        try:
            cur = conn.cursor()

            # Primero se crean las PK.
            for table_def in contract["tables"]:
                schema = table_def["schema"]
                table = table_def["name"]
                primary_key = table_def.get("primary_key")

                if primary_key:
                    cur.execute(build_add_pk_sql(schema, table, primary_key))

            # Después se crean las FK.
            for table_def in contract["tables"]:
                schema = table_def["schema"]
                table = table_def["name"]

                for fk_def in table_def.get("foreign_keys", []):
                    cur.execute(build_add_fk_sql(schema, table, fk_def))

            conn.commit()
            print("Constraints físicas aplicadas OK")

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
        joins = table_def["source"].get("joins", [])
        part_col = table_def["idempotency"]["partition_col"]
        quality_rules = table_def.get("quality_rules", [])
 
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

            # -----------------------------------------
            # QUARANTINE TABLE
            # -----------------------------------------
            cur.execute(build_create_quarantine_sql(schema))
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
            cur.execute(build_delete_quarantine_sql(schema, table, part_col), (table, part_val))
            conn.commit()

            # -----------------------------------------
            # QUARANTINE
            # -----------------------------------------
            executable_rules = [
                rule for rule in quality_rules
                if isinstance(rule, dict) and "quarantine_if" in rule
            ]

            for rule in executable_rules:
                quarantine_sql = build_quarantine_insert_sql(
                    schema, table, src, ts, ds, joins, rule
                )
                cur.execute(quarantine_sql)

            conn.commit()
 
            # -----------------------------------------
            # INSERT
            # -----------------------------------------
            insert_sql = build_insert_sql(schema, table, src, columns, ts, ds, joins, quality_rules)
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
    drop_constraints_op = eliminar_constraints()
    barrios_op = cargar_station_barrios()
    apply_constraints_op = aplicar_constraints()

    schema_op >> drop_constraints_op

    processed_tasks = []

    for table_def in contract["tables"]:
        task_op = procesar_tabla.override(
            task_id=f"procesar_{table_def['name']}"
        )(table_def)

        if table_def["name"] == "stations":
            drop_constraints_op >> barrios_op >> task_op
        else:
            drop_constraints_op >> task_op

        processed_tasks.append(task_op)

    processed_tasks >> apply_constraints_op
 
silver_citybikes_pipeline()
 