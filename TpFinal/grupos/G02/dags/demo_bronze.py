from datetime import datetime
from airflow.sdk import dag, get_current_context, task
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from psycopg2.extras import Json


FAKE_SALES = [
    {"sale_date": "2026-10-01", "city": "Buenos Aires", "product": "Teclado", "quantity": 2, "unit_price": 15000},
    {"sale_date": "2026-10-01", "city": "Cordoba", "product": "Mouse", "quantity": 3, "unit_price": 8000},
    {"sale_date": "2026-10-02", "city": "Rosario", "product": "Monitor", "quantity": 1, "unit_price": 180000},
    {"sale_date": "2026-10-02", "city": "Buenos Aires", "product": "Mouse", "quantity": 2, "unit_price": 8000},
    {"sale_date": "2026-10-03", "city": "Mendoza", "product": "Teclado", "quantity": 1, "unit_price": 15000},
    {"sale_date": "2026-10-03", "city": "Cordoba", "product": "Monitor", "quantity": 1, "unit_price": 180000},
    {"sale_date": "2026-10-04", "city": "Rosario", "product": "Mouse", "quantity": 4, "unit_price": 8000},
    {"sale_date": "2026-10-04", "city": "Mar del Plata", "product": "Teclado", "quantity": 2, "unit_price": 15000},
    {"sale_date": "2026-10-05", "city": "Buenos Aires", "product": "Monitor", "quantity": 1, "unit_price": 180000},
    {"sale_date": "2026-10-05", "city": "Mendoza", "product": "Mouse", "quantity": 2, "unit_price": 8000},
    {"sale_date": "2026-10-05", "city": "Rosario", "product": "Mouse", "quantity": -2, "unit_price": 8000},
    {"sale_date": "2026-10-05", "city": "   ", "product": "Teclado", "quantity": 1, "unit_price": 15000},
]


@dag(
    dag_id="demo_bronze",
    description="Inserta ventas ficticias en bruto y dispara Silver.",
    schedule="@once",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["demo", "bronze", "medallion"],
)
def demo_bronze():
    @task
    def insert_fake_sales() -> int:
        # Identificador de la ejecucion actual del DAG
        batch_id = get_current_context()["run_id"]

        # Conexion con PostgreSQL configurada en Airflow
        hook = PostgresHook(postgres_conn_id="warehouse")

        # Crear la tabla si todavia no existe
        hook.run("""
            CREATE TABLE IF NOT EXISTS bronze.sales_raw (
                id BIGSERIAL PRIMARY KEY,
                batch_id TEXT NOT NULL,
                record_number INTEGER NOT NULL,
                payload JSONB NOT NULL,
                ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (batch_id, record_number)
            );
        """)

        # Preparar los registros ficticios
        rows = [
            (batch_id, index, Json(payload))
            for index, payload in enumerate(FAKE_SALES, start=1)
        ]

        # Insertar los registros en Bronze
        with hook.get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO bronze.sales_raw (
                        batch_id,
                        record_number,
                        payload
                    )
                    VALUES (%s, %s, %s)
                    ON CONFLICT (batch_id, record_number) DO NOTHING
                    """,
                    rows,
                )

        print(
            f"Bronze: {len(rows)} registros ficticios procesados. "
            f"batch_id={batch_id}"
        )

        return len(rows)

    inserted = insert_fake_sales()

    trigger_silver = TriggerDagRunOperator(
        task_id="trigger_silver",
        trigger_dag_id="demo_silver",
        wait_for_completion=True,
        poke_interval=5,
    )

    inserted >> trigger_silver


demo_bronze()