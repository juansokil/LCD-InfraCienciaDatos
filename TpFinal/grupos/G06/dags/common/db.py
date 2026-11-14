"""Conexion al warehouse, compartida por los tres DAGs."""
import os

import sqlalchemy


def get_engine():
    """Engine de SQLAlchemy contra el Postgres del pipeline.

    Los datos salen del .env (via docker-compose). Adentro de la red de Docker
    el host es el nombre del servicio: `warehouse`.
    """
    user = os.getenv("SOURCE_DB_USER", "admin")
    pwd = os.getenv("SOURCE_DB_PASS", "admin")
    host = os.getenv("SOURCE_DB_HOST", "warehouse")
    port = os.getenv("SOURCE_DB_PORT", "5432")
    name = os.getenv("SOURCE_DB_NAME", "openmeteo")
    return sqlalchemy.create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{name}")
