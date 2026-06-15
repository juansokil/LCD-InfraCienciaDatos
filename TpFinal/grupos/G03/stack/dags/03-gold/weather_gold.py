from airflow import DAG
from airflow.decorators import task
from airflow.providers.postgres.hooks.postgres import PostgresHook
from datetime import datetime

default_args = {
    "owner": "grupo03",
    "start_date": datetime(2026, 1, 1),
    "retries": 1,
}

with DAG(
    dag_id="weather_gold_pipeline",
    default_args=default_args,
    schedule="@hourly",
    catchup=False,
    is_paused_upon_creation=False,
) as dag:

    @task
    def cargar_fact_clima_real():

        pg = PostgresHook(postgres_conn_id="postgres_default")
        conn = pg.get_conn()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO gold.fact_clima_real (
                fecha,
                ciudad_id,
                temp_promedio,
                temp_max,
                temp_min,
                lluvia_acumulada,
                viento_promedio
            )
            SELECT
                DATE(w.time) AS fecha,
                c.id AS ciudad_id,
                AVG(w.temperature) AS temp_promedio,
                MAX(w.temperature) AS temp_max,
                MIN(w.temperature) AS temp_min,
                SUM(COALESCE(w.precipitation,0)) AS lluvia_acumulada,
                AVG(w.windspeed) AS viento_promedio
            FROM silver.weather_current w
            JOIN gold.dim_ciudad c
                ON w.ciudad = c.ciudad
            GROUP BY
                DATE(w.time),
                c.id
            ON CONFLICT (fecha, ciudad_id)
            DO UPDATE SET
                temp_promedio = EXCLUDED.temp_promedio,
                temp_max = EXCLUDED.temp_max,
                temp_min = EXCLUDED.temp_min,
                lluvia_acumulada = EXCLUDED.lluvia_acumulada,
                viento_promedio = EXCLUDED.viento_promedio;
        """)

        conn.commit()
        cur.close()
        conn.close()

    @task
    def cargar_fact_pronostico():

        pg = PostgresHook(postgres_conn_id="postgres_default")
        conn = pg.get_conn()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO gold.fact_pronostico (
                fecha_pronostico,
                ciudad_id,
                temp_min_esperada,
                temp_max_esperada,
                prob_lluvia
            )
            SELECT
                f.fecha_pronostico,
                c.id,
                AVG(f.temp_min),
                AVG(f.temp_max),
                AVG(f.prob_lluvia)
            FROM silver.weather_forecast f
            JOIN gold.dim_ciudad c
                ON f.ciudad = c.ciudad
            GROUP BY
                f.fecha_pronostico,
                c.id
            ON CONFLICT (fecha_pronostico, ciudad_id)
            DO UPDATE SET
                temp_min_esperada = EXCLUDED.temp_min_esperada,
                temp_max_esperada = EXCLUDED.temp_max_esperada,
                prob_lluvia = EXCLUDED.prob_lluvia;
        """)

        conn.commit()
        cur.close()
        conn.close()

    clima_real = cargar_fact_clima_real()
    pronostico = cargar_fact_pronostico()

    clima_real >> pronostico