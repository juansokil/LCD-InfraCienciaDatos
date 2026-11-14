"""g06_silver — limpieza y validacion (ESQUELETO).

No tiene reloj: corre cuando Bronze emite BRONZE_OPENMETEO. Por ahora solo deja
una marca en silver.esqueleto_ping. El dueno de Silver reemplaza la tarea por el
SQL real, manteniendo el dag_id y el outlet SILVER_OPENMETEO.
"""
import sys
from datetime import datetime

from airflow.sdk import dag, task
from sqlalchemy import text

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
    def ping():
        with get_engine().begin() as conn:
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS silver.esqueleto_ping (corrida_ts TIMESTAMP DEFAULT now())"))
            conn.execute(text("INSERT INTO silver.esqueleto_ping DEFAULT VALUES"))

    ping()


g06_silver()
