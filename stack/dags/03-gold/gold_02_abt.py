
"""
DAG pedagogico: Gold ABT (Wide Table) para ML
Clase 05 - Feature Engineering: 1 fila por entidad con metricas agregadas.

Pipeline didactico:
  silver.ventas_demo -> gold.abt_clientes_demo (1 fila por cliente)

Conceptos clave:
  - ABT (Analytical Base Table): tabla ancha, denormalizada
  - Feature engineering: derivar features agregados (count, sum, mean, time-based)
  - Categorizacion con pd.cut (segmentacion por valor)
  - Verificacion de integridad referencial
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
    dag_id="gold_02_abt",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["gold"],
    doc_md="DAG didactico: ABT (wide table) con feature engineering para ML.",
)
def gold_02_abt():

    @task
    def prepare_silver():
        """Crea silver.ventas_demo (mismo set que gold_01_star_basico)."""
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

    @task
    def build_abt_clientes():
        """Agrupa por cliente_id y deriva features de comportamiento."""
        import pandas as pd
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)
        df = pd.read_sql("SELECT * FROM silver.ventas_demo", engine)
        df["fecha"] = pd.to_datetime(df["fecha"])
        df["monto"] = df["precio"] * df["cantidad"]

        ahora = pd.Timestamp.now().normalize()

        abt = df.groupby("cliente_id").agg(
            total_compras=("venta_id", "count"),
            monto_total=("monto", "sum"),
            ticket_promedio=("monto", "mean"),
            ultima_compra=("fecha", "max"),
            primera_compra=("fecha", "min"),
        ).reset_index()

        abt["recencia_dias"] = (ahora - abt["ultima_compra"]).dt.days
        abt["ticket_promedio"] = abt["ticket_promedio"].round(2)

        # Segmentacion por monto_total (Bronze / Silver / Gold)
        abt["segmento_valor"] = pd.cut(
            abt["monto_total"],
            bins=[0, 100, 1000, float("inf")],
            labels=["Bronze", "Silver", "Gold"],
        ).astype(str)

        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("CREATE SCHEMA IF NOT EXISTS gold;"))
        abt.to_sql("abt_clientes_demo", engine, schema="gold", if_exists="replace", index=False)
        print(f"gold.abt_clientes_demo: {len(abt)} clientes con features.")

    @task
    def verify_integrity():
        """LEFT JOIN para detectar clientes huerfanos."""
        import pandas as pd
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)
        q = """
            SELECT COUNT(DISTINCT v.cliente_id) AS huerfanos
            FROM silver.ventas_demo v
            LEFT JOIN gold.abt_clientes_demo a ON v.cliente_id = a.cliente_id
            WHERE a.cliente_id IS NULL
        """
        n = int(pd.read_sql(q, engine).iloc[0, 0])
        if n > 0:
            print(f"WARNING: {n} clientes huerfanos detectados.")
        else:
            print("OK: integridad referencial verificada.")

    silver_done = prepare_silver()
    abt_done = build_abt_clientes()
    silver_done >> abt_done >> verify_integrity()


gold_02_abt()
