"""g06_gold — modelo estrella y vistas (ESQUELETO).

Corre cuando Silver emite SILVER_OPENMETEO. Por ahora solo deja una marca en
gold.esqueleto_ping, que el dashboard muestra para confirmar que la cadena
completa llego hasta Gold. El dueno de Gold reemplaza la tarea por el SQL real
(dims, facts, vista del semaforo, chequeo de huerfanos), manteniendo el dag_id
y el outlet GOLD_OPENMETEO.
"""
import sys
from datetime import datetime

from airflow.sdk import dag, task
from sqlalchemy import text

sys.path.append("/opt/airflow/dags")
from common.assets import GOLD_OPENMETEO, SILVER_OPENMETEO  # noqa: E402
from common.db import get_engine  # noqa: E402


@dag(
    dag_id="g06_gold",
    start_date=datetime(2026, 1, 1),
    schedule=[SILVER_OPENMETEO],
    catchup=False,
    is_paused_upon_creation=False,
    tags=["g06", "gold"],
)
def g06_gold():

    @task(outlets=[GOLD_OPENMETEO])
    def ping():
        with get_engine().begin() as conn:
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS gold.esqueleto_ping (corrida_ts TIMESTAMP DEFAULT now())"))
            conn.execute(text("INSERT INTO gold.esqueleto_ping DEFAULT VALUES"))

    ping()


g06_gold()
