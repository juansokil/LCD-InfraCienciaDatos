import os

import sqlalchemy


def get_engine():
    user = os.getenv("SOURCE_DB_USER", "admin")
    password = os.getenv("SOURCE_DB_PASS", "admin")
    host = os.getenv("SOURCE_DB_HOST", "data_warehouse")
    db = os.getenv("SOURCE_DB_NAME", "InfraCienciaDatos")
    return sqlalchemy.create_engine(f"postgresql+psycopg2://{user}:{password}@{host}:5432/{db}")
