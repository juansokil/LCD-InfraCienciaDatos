"""g06_bronze — ingesta de Open-Meteo (ESQUELETO).

Por ahora solo deja una marca en bronze.esqueleto_ping para probar que el
encadenado funciona. El dueno de Bronze reemplaza la tarea por la ingesta real
(forecast + previous-runs para los 3 destinos), manteniendo el dag_id y el
outlet BRONZE_OPENMETEO.
"""
import sys
from datetime import datetime

from airflow.sdk import dag, task
from sqlalchemy import text

sys.path.append("/opt/airflow/dags")
from common.assets import BRONZE_OPENMETEO  # noqa: E402
from common.db import get_engine  # noqa: E402


@dag(
    dag_id="g06_bronze",
    start_date=datetime(2026, 1, 1),
    schedule="0 * * * *",          # cada hora: Open-Meteo se actualiza por hora
    catchup=False,                 # no correr la historia desde start_date
    is_paused_upon_creation=False, # nace activo: nadie tiene que despausarlo
    tags=["g06", "bronze"],
)
def g06_bronze():

    @task(outlets=[BRONZE_OPENMETEO])
    def ping():
        with get_engine().begin() as conn:
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS bronze.esqueleto_ping (corrida_ts TIMESTAMP DEFAULT now())"))
            conn.execute(text("INSERT INTO bronze.esqueleto_ping DEFAULT VALUES"))

    ping()


g06_bronze()
