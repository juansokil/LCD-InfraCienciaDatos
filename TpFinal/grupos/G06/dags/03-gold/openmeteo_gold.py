"""g06_gold — modelo estrella + vistas.

Corre cuando Silver emite SILVER_OPENMETEO. Lee silver.clima_diario (ver
Contrato-silver-propuesta.md) y arma:

    gold.dim_ciudad, gold.dim_tiempo, gold.fact_clima_diario   (grano: ciudad x dia)
    gold.v_mejor_epoca, gold.v_alertas_temperatura, gold.v_lluvia_mensual
    gold.umbrales   (umbrales de negocio editables: temp. extrema, dia agradable)

El SQL vive en dags/03-gold/sql/ (01 modelo, 02 carga, 03 vistas, 04 chequeos).
Todo es idempotente: se puede re-correr sin duplicar filas.
"""
import sys
from datetime import datetime
from pathlib import Path

from airflow.sdk import dag, task

sys.path.append("/opt/airflow/dags")
from common.assets import GOLD_OPENMETEO, SILVER_OPENMETEO  # noqa: E402
from common.db import get_engine  # noqa: E402

SQL_DIR = Path(__file__).parent / "sql"


def correr_sql(nombre_archivo: str) -> None:
    """Ejecuta un archivo .sql completo en una sola transaccion."""
    sql = (SQL_DIR / nombre_archivo).read_text(encoding="utf-8")
    with get_engine().begin() as conn:
        conn.exec_driver_sql(sql)


@dag(
    dag_id="g06_gold",
    start_date=datetime(2026, 1, 1),
    schedule=[SILVER_OPENMETEO],
    catchup=False,
    is_paused_upon_creation=False,
    tags=["g06", "gold"],
)
def g06_gold():

    @task
    def crear_modelo():
        correr_sql("01_modelo.sql")

    @task
    def cargar_dims_y_fact():
        correr_sql("02_cargar.sql")

    @task
    def crear_vistas():
        correr_sql("03_vistas.sql")

    @task(outlets=[GOLD_OPENMETEO])
    def chequear_huerfanos():
        """Falla el DAG si hay hechos sin dimension o filas perdidas desde Silver."""
        sql = (SQL_DIR / "04_chequeos.sql").read_text(encoding="utf-8")
        with get_engine().begin() as conn:
            filas = conn.exec_driver_sql(sql).fetchall()
        problemas = {chequeo: n for chequeo, n in filas if n > 0}
        if problemas:
            raise ValueError(f"Chequeos de Gold fallidos: {problemas}")

    crear_modelo() >> cargar_dims_y_fact() >> crear_vistas() >> chequear_huerfanos()


g06_gold()
