import os
from pathlib import Path

import psycopg2
from airflow.sdk import dag, task


@dag(
    dag_id="silver_usgs_g07",
    schedule=None,
    catchup=False,
    tags=["G07", "silver"]
)
def silver_usgs_g07():

    @task
    def transformar_sismos():

        archivo_sql = Path(
            "/opt/airflow/sql/03_transform_silver.sql"
        )

        consulta = archivo_sql.read_text(encoding="utf-8")

        conexion = psycopg2.connect(
            os.environ["USGS_DB_DSN"]
        )

        try:
            with conexion:
                with conexion.cursor() as cursor:
                    cursor.execute(consulta)
                    print(
                        "Registros insertados o actualizados:",
                        cursor.rowcount
                    )
        finally:
            conexion.close()

    transformar_sismos()


silver_usgs_g07()