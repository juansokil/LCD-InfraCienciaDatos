
"""
DAG pedagogico: Silver con Pydantic CONTRACT-DRIVEN + Quarantine
Clase 04 - Validacion estricta usando el contrato YAML compartido con Bronze.

Pipeline:
  bronze.ventas_demo
    -> Pydantic generado dinamicamente desde ventas.yaml
    -> { silver.ventas_contrato | silver.quarantine_ventas_contrato }

Diferencia con la version anterior:
  - YA NO hay `class VentaContract(BaseModel)` hardcodeado.
  - El contrato se LEE de stack/data/contracts/ventas.yaml.
  - Pydantic se construye en runtime con build_pydantic_from_contract().
  - Cambiar el contrato (agregar columnas, ajustar reglas) = editar YAML.
"""

from airflow.decorators import dag, task
from datetime import datetime
import os
import sys

# Hacemos visible el paquete `common` (esta dos niveles arriba)
sys.path.append("/opt/airflow/dags")
from common.contracts import build_pydantic_from_contract, load_contract  # noqa: E402


DB_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
    f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
    f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
    f"{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
)

CONTRACT_PATH = "/opt/airflow/data/contracts/ventas.yaml"


@dag(
    dag_id="silver_02_contrato",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["silver"],
    doc_md="DAG didactico: Pydantic generado dinamicamente desde ventas.yaml + quarantine.",
)
def silver_02_contrato():

    @task
    def prepare_bronze():
        """Crea bronze.ventas_demo con datos sucios (incluye filas invalidas)."""
        import pandas as pd
        import sqlalchemy

        # 8 filas: 3 fallan el contrato ventas.yaml (van a quarantine):
        #   venta_id=4 -> cliente_email "no-es-email": type:email invalido
        #   venta_id=6 -> producto " " (min_length:2) + precio -50 (gt:0)
        #                 + fecha "invalid-date" (type:date)  [3 violaciones]
        #   venta_id=7 -> precio None: el contrato lo exige (nullable:false)
        # Las otras 5 (1,2,3,5,8) pasan -> silver.ventas_contrato
        data = {
            "venta_id": [1, 2, 3, 4, 5, 6, 7, 8],
            "producto": ["Laptop", "Mouse", "Teclado", "Monitor",
                         "Auriculares", " ", "Mouse", "Tablet"],
            "precio": [1500.50, 25.00, 75.00, 350.00,
                       120.00, -50.00, None, 85.50],
            "cantidad": [1, 2, 1, 1, 3, 1, 5, 2],
            "fecha": ["2024-01-15", "2024-01-16", "2024-01-17", "2024-01-18",
                      "2024-01-19", "invalid-date", "2024-01-21", "2024-01-22"],
            "cliente_email": ["juan@example.com", "maria@example.com",
                              "pedro@example.com", "no-es-email",
                              "ana@example.com", "luis@example.com",
                              "sofia@example.com", "carlos@example.com"],
        }
        df = pd.DataFrame(data)

        engine = sqlalchemy.create_engine(DB_URI)
        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("CREATE SCHEMA IF NOT EXISTS bronze;"))
        df.to_sql("ventas_demo", engine, schema="bronze", if_exists="replace", index=False)  # idempotente: replace -> re-run no duplica
        print(f"bronze.ventas_demo: {len(df)} filas (algunas invalidas).")

    @task
    def validate_with_contract():
        """Lee contrato YAML, construye Pydantic, valida fila por fila."""
        import pandas as pd
        import sqlalchemy

        # 1) Leer contrato Y construir Pydantic en runtime (corazon del refactor)
        contract = load_contract(CONTRACT_PATH)
        VentaContract = build_pydantic_from_contract(contract)
        print(f"Contrato cargado: {contract['dataset']} v{contract['version']}")
        print(f"Modelo Pydantic generado con campos: {list(VentaContract.model_fields.keys())}")

        # 2) Leer Bronze
        engine = sqlalchemy.create_engine(DB_URI)
        df = pd.read_sql("SELECT * FROM bronze.ventas_demo", engine)

        # 3) Validar fila por fila
        validos, invalidos = [], []
        for _, row in df.iterrows():
            try:
                ok = VentaContract(**row.to_dict())
                d = ok.model_dump()
                # serializar fechas a ISO para la DB
                if d.get("fecha"):
                    d["fecha"] = d["fecha"].isoformat()
                validos.append(d)
            except Exception as e:
                inv = {k: (v if not pd.isna(v) else None) for k, v in row.to_dict().items()}
                inv["error_type"] = type(e).__name__
                inv["error_message"] = str(e)[:300]
                invalidos.append(inv)

        print(f"Validos: {len(validos)} | Invalidos: {len(invalidos)}")
        return {"validos": validos, "invalidos": invalidos}

    @task
    def load_silver(payload: dict):
        """Carga validos en silver.ventas_contrato + audit metadata."""
        import pandas as pd
        import sqlalchemy
        from datetime import datetime as dt

        engine = sqlalchemy.create_engine(DB_URI)
        df = pd.DataFrame(payload["validos"])
        if df.empty:
            print("Sin validos para silver.")
            return
        df["silver_at"] = dt.now().isoformat()

        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("CREATE SCHEMA IF NOT EXISTS silver;"))
        df.to_sql("ventas_contrato", engine, schema="silver", if_exists="replace", index=False)  # idempotente: replace -> re-run no duplica
        print(f"silver.ventas_contrato: {len(df)} filas validas.")

    @task
    def load_quarantine(payload: dict):
        """Carga invalidos en silver.quarantine_ventas_contrato + error info."""
        import pandas as pd
        import sqlalchemy
        from datetime import datetime as dt

        engine = sqlalchemy.create_engine(DB_URI)
        df = pd.DataFrame(payload["invalidos"])
        if df.empty:
            print("Sin invalidos en cuarentena.")
            return
        df["quarantined_at"] = dt.now().isoformat()

        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("CREATE SCHEMA IF NOT EXISTS silver;"))
        df.to_sql("quarantine_ventas_contrato", engine, schema="silver", if_exists="replace", index=False)  # idempotente: replace -> re-run no duplica
        print(f"silver.quarantine_ventas_contrato: {len(df)} filas invalidas.")

    bronze_done = prepare_bronze()
    payload = validate_with_contract()
    bronze_done >> payload
    load_silver(payload)
    load_quarantine(payload)


silver_02_contrato()
