"""
Utilidades compartidas por los DAGs de CityBikes.
Vive en la raiz de dags/ que esta en el PYTHONPATH de Airflow,
asi que desde cualquier DAG se importa con:  from citybikes_common import ...
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

API_BASE = "https://api.citybik.es/v2"

# Redes a trackear (ids de /v2/networks). Configurable por entorno.
NETWORKS = [
    n.strip()
    for n in os.environ.get("CITYBIKES_NETWORKS", "ecobici-buenos-aires,mibicitubici,bikesampa").split(",")
    if n.strip()
]


def get_warehouse_engine() -> Engine:
    """Engine SQLAlchemy al warehouse de datos (NO al metadata de Airflow)."""
    user = os.environ.get("WAREHOUSE_USER", "cb_user")
    pwd = os.environ.get("WAREHOUSE_PASSWORD", "changeme")
    host = os.environ.get("WAREHOUSE_HOST", "warehouse")
    port = os.environ.get("WAREHOUSE_PORT", "5432")
    db = os.environ.get("WAREHOUSE_DB", "citybikes")
    url = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"
    return create_engine(url, pool_pre_ping=True)
