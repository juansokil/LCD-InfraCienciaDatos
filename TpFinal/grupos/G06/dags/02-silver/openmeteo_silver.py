"""g06_silver — limpieza y validacion.

Se ejecuta cuando Bronze emite BRONZE_OPENMETEO.
Crea el modelo Silver, limpia los datos, realiza validaciones
y carga los registros en la tabla definitiva.
"""

import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from airflow.sdk import dag, task

sys.path.append("/opt/airflow/dags")
from common.assets import BRONZE_OPENMETEO, SILVER_OPENMETEO  # noqa: E402
from common.db import get_engine  # noqa: E402


@dag(
    dag_id="g06_silver",
    start_date=datetime(2026, 1, 1),
    schedule=[BRONZE_OPENMETEO],   # se dispara por el dato, no por la hora
    catchup=False,
    is_paused_upon_creation=False,
    tags=["g06", "silver"],
)
def g06_silver():

    def ejecutar_archivo(nombre_archivo):
        sql_path = Path(__file__).parent / "sql" / nombre_archivo
        sql = sql_path.read_text(encoding="utf-8")

        with get_engine().begin() as conn:
            conn.exec_driver_sql(sql)

    @task
    def crear_modelo():
        ejecutar_archivo("01_modelo.sql")

    @task
    def limpiar_datos():
        ejecutar_archivo("02_limpieza.sql")

    @task
    def validar_datos():
        sql_path = Path(__file__).parent / "sql" / "03_validaciones.sql"
        sql = sql_path.read_text(encoding="utf-8")

        with get_engine().connect() as conn:
            resultado = conn.execute(text(sql)).mappings().one()

            print("Resultados de las validaciones Silver:")
            for nombre, valor in resultado.items():
                print(f"{nombre}: {valor}")

    @task(outlets=[SILVER_OPENMETEO])
    def cargar_datos():
        ejecutar_archivo("04_cargar.sql")

    modelo = crear_modelo()
    limpieza = limpiar_datos()
    validacion = validar_datos()
    carga = cargar_datos()

    modelo >> limpieza >> validacion >> carga



g06_silver()