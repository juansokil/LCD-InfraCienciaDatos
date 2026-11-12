
import os
from pathlib import Path
from datetime import datetime, timezone

from airflow.sdk import dag, task

from common.db import get_warehouse_engine
from common.assets import SILVER_CLIMA, GOLD_CLIMA


def ejecutar_sql_gold(nombre_archivo):
    """Ejecuta un archivo SQL sobre el warehouse PostgreSQL."""

    ruta = (
        Path(os.environ["PROJECT_ROOT"])
        / "sql"
        / nombre_archivo
    )

    if not ruta.is_file():
        raise FileNotFoundError(f"No existe: {ruta}")

    contenido_sql = ruta.read_text(encoding="utf-8")

    engine = get_warehouse_engine()
    conexion = engine.raw_connection()

    try:
        with conexion.cursor() as cursor:
            cursor.execute(contenido_sql, prepare=False)

        conexion.commit()

    except Exception:
        conexion.rollback()
        raise

    finally:
        conexion.close()
        engine.dispose()


@dag(
    dag_id="gold_clima",
    schedule=[SILVER_CLIMA],
    start_date=datetime(2026, 11, 4, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["tpfinal", "open-meteo", "G04", "gold"],
)
def gold_clima():

    @task(task_id="cargar_gold")
    def cargar_gold():
        ejecutar_sql_gold("gold_clima.sql")

    @task(
        task_id="actualizar_vistas",
        outlets=[GOLD_CLIMA],
    )
    def actualizar_vistas():
        ejecutar_sql_gold("gold_views.sql")

    cargar_gold() >> actualizar_vistas()


gold_clima_dag = gold_clima()
