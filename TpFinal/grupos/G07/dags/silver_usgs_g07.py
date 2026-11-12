import os
from pathlib import Path

import psycopg2
from airflow.sdk import dag, task
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator


@dag(
    dag_id="silver_usgs_g07",
    schedule=None,
    catchup=False,
    tags=["G07", "silver"],
)
def silver_usgs_g07():

    @task
    def transformar_sismos():
        archivo_sql = Path("/opt/airflow/sql/03_transform_silver.sql")
        consulta = archivo_sql.read_text(encoding="utf-8")

        conexion = psycopg2.connect(os.environ["USGS_DB_DSN"])

        try:
            with conexion:
                with conexion.cursor() as cursor:
                    cursor.execute(consulta)
                    print(
                        "Registros insertados o actualizados en Silver:",
                        cursor.rowcount,
                    )
        finally:
            conexion.close()

    @task
    def validar_calidad_silver():
        """Valida que los datos en Silver cumplan reglas de negocio (Clase 3)"""
        conexion = psycopg2.connect(os.environ["USGS_DB_DSN"])
        try:
            with conexion:
                with conexion.cursor() as cursor:
                    # Regla de Validez (Rango): La magnitud no debería ser mayor a 10
                    cursor.execute("SELECT COUNT(*) FROM silver.sismos WHERE magnitud > 10;")
                    sismos_erroneos = cursor.fetchone()[0]
                    assert sismos_erroneos == 0, f"Error de Calidad: Se encontraron {sismos_erroneos} sismos con magnitud irreal (>10)."
                    print("✓ Control de calidad Silver aprobado: Magnitudes en rangos válidos.")
        finally:
            conexion.close()

    iniciar_gold = TriggerDagRunOperator(
        task_id="iniciar_gold",
        trigger_dag_id="gold_usgs_g07",
        wait_for_completion=True,
        poke_interval=10,
    )

    transformar_sismos() >> validar_calidad_silver() >> iniciar_gold


silver_usgs_g07()