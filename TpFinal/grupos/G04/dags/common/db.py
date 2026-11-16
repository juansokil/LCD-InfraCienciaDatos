
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import URL


def get_warehouse_engine():
    variables = [
        "WAREHOUSE_HOST",
        "WAREHOUSE_PORT",
        "WAREHOUSE_DB",
        "WAREHOUSE_USER",
        "WAREHOUSE_PASSWORD",
    ]

    faltantes = [v for v in variables if not os.getenv(v)]

    if faltantes:
        raise RuntimeError(
            "Faltan variables de entorno: " + ", ".join(faltantes)
        )

    url = URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["WAREHOUSE_USER"],
        password=os.environ["WAREHOUSE_PASSWORD"],
        host=os.environ["WAREHOUSE_HOST"],
        port=int(os.environ["WAREHOUSE_PORT"]),
        database=os.environ["WAREHOUSE_DB"],
    )

    return create_engine(url, pool_pre_ping=True)
