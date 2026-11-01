from datetime import datetime
from airflow.sdk import dag, task
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator

@dag(
    dag_id="demo_silver",
    description="Limpia las ventas Bronze y dispara Gold.",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["demo", "silver", "medallion"],
)
def demo_silver():
    @task
    def clean_sales() -> None:
        hook = PostgresHook(postgres_conn_id="warehouse")

        # Crear la tabla si todavia no existe
        hook.run("""
            CREATE TABLE IF NOT EXISTS silver.sales_clean (
                bronze_id BIGINT PRIMARY KEY
                    REFERENCES bronze.sales_raw(id),
                sale_date DATE NOT NULL,
                city TEXT NOT NULL,
                product TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
                total_amount NUMERIC(14,2) NOT NULL CHECK (total_amount >= 0),
                cleaned_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)

        # Conexion con PostgreSQL y ejecucion de la transformación
        with hook.get_conn() as conn:
            with conn.cursor() as cursor:

                cursor.execute("""
                    WITH extracted AS (
                        SELECT
                            id AS bronze_id,

                            CASE
                                WHEN payload->>'sale_date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                                THEN (payload->>'sale_date')::date
                            END AS sale_date,

                            NULLIF(BTRIM(payload->>'city'), '') AS city,
                            NULLIF(BTRIM(payload->>'product'), '') AS product,

                            CASE
                                WHEN payload->>'quantity' ~ '^-?[0-9]+$'
                                THEN (payload->>'quantity')::integer
                            END AS quantity,

                            CASE
                                WHEN payload->>'unit_price' ~ '^[0-9]+([.][0-9]{1,2})?$'
                                THEN (payload->>'unit_price')::numeric(12,2)
                            END AS unit_price

                        FROM bronze.sales_raw
                    )

                    INSERT INTO silver.sales_clean (
                        bronze_id,
                        sale_date,
                        city,
                        product,
                        quantity,
                        unit_price,
                        total_amount
                    )

                    SELECT
                        bronze_id,
                        sale_date,
                        city,
                        product,
                        quantity,
                        unit_price,
                        quantity * unit_price

                    FROM extracted

                    WHERE sale_date IS NOT NULL
                      AND city IS NOT NULL
                      AND product IS NOT NULL
                      AND quantity > 0
                      AND unit_price >= 0

                    ON CONFLICT (bronze_id)
                    DO UPDATE SET
                        sale_date = EXCLUDED.sale_date,
                        city = EXCLUDED.city,
                        product = EXCLUDED.product,
                        quantity = EXCLUDED.quantity,
                        unit_price = EXCLUDED.unit_price,
                        total_amount = EXCLUDED.total_amount,
                        cleaned_at = NOW();
                """)

                # Consultar cantidad de registros procesados
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM silver.sales_clean;
                """)

                count = cursor.fetchone()[0]

        print(f"Silver: hay {count} ventas limpias.")

    cleaned = clean_sales()

    # Ejecutar Gold cuando Silver termine correctamente
    trigger_gold = TriggerDagRunOperator(
        task_id="trigger_gold",
        trigger_dag_id="demo_gold",
        wait_for_completion=True,
        poke_interval=5,
    )

    cleaned >> trigger_gold


demo_silver()