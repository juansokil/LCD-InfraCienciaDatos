import os
from pathlib import Path

import psycopg2
from airflow.sdk import dag, task


@dag(
    dag_id="gold_usgs_g07",
    schedule=None,
    catchup=False,
    tags=["G07", "gold"],
)
def gold_usgs_g07():

    @task
    def construir_gold():
        dsn = os.environ["USGS_DB_DSN"]
        ddl = Path("/opt/airflow/sql/04_create_gold.sql").read_text(encoding="utf-8")
        dml = Path("/opt/airflow/sql/05_transform_gold.sql").read_text(encoding="utf-8")

        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
                cur.execute(dml)
                print("Gold construido. Filas afectadas (DML):", cur.rowcount)

    @task
    def validar_gold():
        dsn = os.environ["USGS_DB_DSN"]
        checks = {
            "unicidad":    "SELECT COUNT(*) , COUNT(DISTINCT sismo_id) FROM gold.fact_sismos",
            "int_fecha":   """SELECT COUNT(*) FROM gold.fact_sismos f
                              LEFT JOIN gold.dim_fecha d ON d.fecha_id = f.fecha_id
                              WHERE d.fecha_id IS NULL""",
            "int_region":  """SELECT COUNT(*) FROM gold.fact_sismos f
                              LEFT JOIN gold.dim_region r ON r.region_id = f.region_id
                              WHERE r.region_id IS NULL""",
            "reconcilia":  """SELECT
                                  (SELECT COUNT(*) FROM silver.sismos) AS s,
                                  (SELECT COUNT(*) FROM gold.fact_sismos) AS g""",
        }
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(checks["unicidad"]);  tot, uniq = cur.fetchone()
                assert tot == uniq, f"Duplicados: {tot} vs {uniq}"
                cur.execute(checks["int_fecha"]);  assert cur.fetchone()[0] == 0, "Huérfanos dim_fecha"
                cur.execute(checks["int_region"]); assert cur.fetchone()[0] == 0, "Huérfanos dim_region"
                cur.execute(checks["reconcilia"]); s, g = cur.fetchone()
                assert s == g, f"Reconciliación: silver={s} gold={g}"
        print("✓ Todos los controles de Gold pasaron.")

    construir_gold() >> validar_gold()


gold_usgs_g07()