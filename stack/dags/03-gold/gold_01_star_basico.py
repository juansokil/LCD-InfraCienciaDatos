
"""
DAG pedagogico: Gold Star Schema Basico
Clase 05 - Construccion de un star schema dimensional.

Pipeline didactico:
  silver.ventas_demo -> dim_producto_demo + dim_tiempo_demo + fact_ventas_demo

Conceptos clave:
  - Surrogate keys (producto_id autogenerado)
  - Dimension tables (1 fila = 1 entidad descriptiva)
  - Fact table (1 fila = 1 evento, con FKs a dimensiones)
"""

from airflow.decorators import dag, task
from datetime import datetime
import os


DB_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
    f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
    f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
    f"{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
)


@dag(
    dag_id="gold_01_star_basico",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["gold"],
    doc_md="DAG didactico: Star Schema (dim + fact) sobre datos sinteticos.",
)
def gold_01_star_basico():

    @task
    def prepare_silver():
        """Crea silver.ventas_demo con datos limpios (10 filas, 5 clientes)."""
        import pandas as pd
        import sqlalchemy

        data = {
            "venta_id": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "cliente_id": [101, 102, 103, 101, 104, 105, 102, 103, 101, 104],
            "producto": ["Laptop", "Mouse", "Teclado", "Monitor", "Auriculares",
                         "Laptop", "Mouse", "Teclado", "Auriculares", "Monitor"],
            "precio": [1500.50, 25.00, 75.00, 350.00, 120.00,
                       1450.00, 30.00, 80.00, 110.00, 360.00],
            "cantidad": [1, 2, 1, 1, 3, 1, 4, 1, 2, 1],
            "fecha": ["2024-01-15", "2024-01-16", "2024-01-17", "2024-01-18", "2024-01-19",
                      "2024-02-01", "2024-02-05", "2024-02-10", "2024-03-01", "2024-03-05"],
        }
        df = pd.DataFrame(data)
        df["fecha"] = pd.to_datetime(df["fecha"])

        engine = sqlalchemy.create_engine(DB_URI)
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("CREATE SCHEMA IF NOT EXISTS silver;"))
        df.to_sql("ventas_demo", engine, schema="silver", if_exists="replace", index=False)
        print(f"silver.ventas_demo: {len(df)} filas listas.")

    @task
    def build_dim_producto():
        """Productos unicos -> gold.dim_producto_demo (con producto_id surrogate)."""
        import pandas as pd
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)
        df = pd.read_sql(
            "SELECT DISTINCT producto FROM silver.ventas_demo ORDER BY producto",
            engine,
        )
        df["producto_id"] = range(1, len(df) + 1)
        df = df[["producto_id", "producto"]]

        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("CREATE SCHEMA IF NOT EXISTS gold;"))
        df.to_sql("dim_producto_demo", engine, schema="gold", if_exists="replace", index=False)
        print(f"gold.dim_producto_demo: {len(df)} productos.")

    @task
    def build_dim_tiempo():
        """Fechas unicas + atributos temporales -> gold.dim_tiempo_demo."""
        import pandas as pd
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)
        df = pd.read_sql(
            "SELECT DISTINCT fecha FROM silver.ventas_demo ORDER BY fecha",
            engine,
        )
        df["fecha"] = pd.to_datetime(df["fecha"])
        df["fecha_id"] = df["fecha"].dt.strftime("%Y%m%d").astype(int)
        df["anio"] = df["fecha"].dt.year
        df["mes"] = df["fecha"].dt.month
        df["trimestre"] = df["fecha"].dt.quarter
        df["dia_semana"] = df["fecha"].dt.day_name()
        df = df[["fecha_id", "fecha", "anio", "mes", "trimestre", "dia_semana"]]

        df.to_sql("dim_tiempo_demo", engine, schema="gold", if_exists="replace", index=False)
        print(f"gold.dim_tiempo_demo: {len(df)} fechas.")

    @task
    def build_fact_ventas():
        """Hechos con FKs a dim_producto_demo y dim_tiempo_demo + monto_total derivado."""
        import pandas as pd
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)
        df = pd.read_sql("SELECT * FROM silver.ventas_demo", engine)
        dim_p = pd.read_sql("SELECT * FROM gold.dim_producto_demo", engine)

        df["fecha"] = pd.to_datetime(df["fecha"])
        df["fecha_id"] = df["fecha"].dt.strftime("%Y%m%d").astype(int)
        df = df.merge(dim_p, on="producto", how="left")
        df["monto_total"] = df["precio"] * df["cantidad"]

        fact = df[["venta_id", "fecha_id", "producto_id", "cliente_id",
                   "precio", "cantidad", "monto_total"]]
        fact.to_sql("fact_ventas_demo", engine, schema="gold", if_exists="replace", index=False)
        print(f"gold.fact_ventas_demo: {len(fact)} filas.")

    silver_done = prepare_silver()
    p = build_dim_producto()
    t = build_dim_tiempo()
    silver_done >> [p, t]
    [p, t] >> build_fact_ventas()


gold_01_star_basico()
