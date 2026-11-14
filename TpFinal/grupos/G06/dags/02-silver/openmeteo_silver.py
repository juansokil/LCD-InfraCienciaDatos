"""g06_silver — limpieza y validacion.

Se ejecuta cuando Bronze emite BRONZE_OPENMETEO.
Por ahora ejecuta el SQL inicial de creacion de la tabla Silver.
La limpieza y carga de datos se completaran cuando este disponible
la ingesta real de Bronze.
"""

import sys
from datetime import datetime
from pathlib import Path

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

    @task(outlets=[SILVER_OPENMETEO])
    def ejecutar_sql():
        sql_path = Path(__file__).parent / "sql" / "01_modelo.sql"
        sql = sql_path.read_text(encoding="utf-8")

        with get_engine().begin() as conn:
            conn.exec_driver_sql(sql)

    ejecutar_sql()


g06_silver()
