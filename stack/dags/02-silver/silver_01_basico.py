
"""
DAG pedagogico: Silver Basico
Clase 04 - Limpieza basica de datos crudos a Silver.

Pipeline didactico (datos sinteticos):
  bronze.ventas_demo (sucio) -> normalizar + fillna + parse fechas -> silver.ventas_basico
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
    dag_id="silver_01_basico",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["silver"],
    doc_md="DAG didactico: limpieza basica Bronze -> Silver con datos sinteticos.",
)
def silver_01_basico():

    @task
    def prepare_bronze():
        """Crea bronze.ventas_demo con datos crudos sucios (8 filas)."""
        import pandas as pd
        import sqlalchemy

        data = {
            "venta_id": [1, 2, 3, 4, 5, 6, 7, 8],
            "producto": ["  Laptop  ", "MOUSE", "Teclado", "Monitor",
                         None, "laptop", "Mouse", "Auriculares"],
            "precio": [1500.50, 25.00, 75.00, 350.00,
                       120.00, 1450.00, 50.00, 85.50],
            "cantidad": [1, 2, None, 1, 3, 1, 5, 2],
            "fecha": ["2024-01-15", "15/01/2024", "2024-01-17", "2024-01-18",
                      "2024-01-19", "2024-01-20", "2024-01-21", "2024-01-22"],
            "cliente_email": ["juan@example.com", "MARIA@EXAMPLE.COM",
                              "pedro@example.com", None, "ana@example.com",
                              "luis@example.com", "sofia@example.com",
                              "carlos@EXAMPLE.COM"],
        }
        df = pd.DataFrame(data)

        engine = sqlalchemy.create_engine(DB_URI)
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("CREATE SCHEMA IF NOT EXISTS bronze;"))
        df.to_sql("ventas_demo", engine, schema="bronze", if_exists="replace", index=False)  # idempotente: replace -> re-run no duplica
        print(f"bronze.ventas_demo creada con {len(df)} filas crudas.")

    @task
    def clean_silver():
        """Lee bronze, aplica limpieza basica, escribe silver."""
        import pandas as pd
        import sqlalchemy
        from dateutil import parser

        engine = sqlalchemy.create_engine(DB_URI)
        df = pd.read_sql("SELECT * FROM bronze.ventas_demo", engine)

        # 1. Strings: strip + Title Case + nulos -> "Desconocido"
        df["producto"] = df["producto"].fillna("Desconocido").str.strip().str.title()
        df["cliente_email"] = df["cliente_email"].fillna("").str.strip().str.lower()

        # 2. Cantidad: nulos -> 1, tipado entero
        df["cantidad"] = df["cantidad"].fillna(1).astype(int)

        # 3. Fechas: parser flexible (acepta "2024-01-15" y "15/01/2024")
        def parse_fecha(s):
            try:
                return parser.parse(str(s)).date()
            except Exception:
                return None
        df["fecha"] = df["fecha"].apply(parse_fecha)

        # 4. Cargar
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("CREATE SCHEMA IF NOT EXISTS silver;"))
        df.to_sql("ventas_basico", engine, schema="silver", if_exists="replace", index=False)  # idempotente: replace -> re-run no duplica (deterministico)
        print(f"silver.ventas_basico cargada con {len(df)} filas limpias.")

    prepare_bronze() >> clean_silver()


silver_01_basico()
