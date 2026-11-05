from datetime import datetime
from airflow.sdk import dag, task
from airflow.providers.postgres.hooks.postgres import PostgresHook

@dag(
    dag_id="demo_gold",
    description="Agrega las ventas Silver para consumo analitico.",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    tags=["demo", "gold", "medallion"],
)
def demo_gold():
    @task
    def build_gold() -> None:
        hook = PostgresHook(postgres_conn_id="warehouse")

        # Crear las tablas si todavia no existen
        hook.run("""
            CREATE TABLE IF NOT EXISTS gold.dim_city (
                city TEXT PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS gold.dim_date (
                sale_date DATE PRIMARY KEY,
                year_num SMALLINT NOT NULL,
                month_num SMALLINT NOT NULL,
                day_num SMALLINT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS gold.fact_sales_daily (
                sale_date DATE NOT NULL
                    REFERENCES gold.dim_date(sale_date),
                city TEXT NOT NULL
                    REFERENCES gold.dim_city(city),
                transactions INTEGER NOT NULL,
                units_sold INTEGER NOT NULL,
                total_revenue NUMERIC(14,2) NOT NULL,
                average_ticket NUMERIC(14,2) NOT NULL,
                PRIMARY KEY (sale_date, city)
            );
        """)

        # Conexion con PostgreSQL y ejecucion de las transformaciones
        with hook.get_conn() as conn:
            with conn.cursor() as cursor:

                # Cargar dimension de ciudades
                cursor.execute("""
                    INSERT INTO gold.dim_city (city)
                    SELECT DISTINCT city
                    FROM silver.sales_clean
                    ON CONFLICT (city) DO NOTHING;
                """)

                # Cargar dimension de fechas
                cursor.execute("""
                    INSERT INTO gold.dim_date (
                        sale_date,
                        year_num,
                        month_num,
                        day_num
                    )
                    SELECT DISTINCT
                        sale_date,
                        EXTRACT(YEAR FROM sale_date)::smallint,
                        EXTRACT(MONTH FROM sale_date)::smallint,
                        EXTRACT(DAY FROM sale_date)::smallint
                    FROM silver.sales_clean

                    ON CONFLICT (sale_date)
                    DO UPDATE SET
                        year_num = EXCLUDED.year_num,
                        month_num = EXCLUDED.month_num,
                        day_num = EXCLUDED.day_num;
                """)

                # Limpiar los datos anteriores de la tabla de hechos
                cursor.execute("""
                    DELETE FROM gold.fact_sales_daily;
                """)

                # Generar las ventas agregadas por fecha y ciudad
                cursor.execute("""
                    INSERT INTO gold.fact_sales_daily (
                        sale_date,
                        city,
                        transactions,
                        units_sold,
                        total_revenue,
                        average_ticket
                    )
                    SELECT
                        sale_date,
                        city,
                        COUNT(*)::integer,
                        SUM(quantity)::integer,
                        SUM(total_amount),
                        AVG(total_amount)
                    FROM silver.sales_clean
                    GROUP BY sale_date, city;
                """)

                # Consultar la cantidad de registros generados
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM gold.fact_sales_daily;
                """)

                count = cursor.fetchone()[0]

        print(f"Gold: se generaron {count} filas agregadas.")

    build_gold()


demo_gold()