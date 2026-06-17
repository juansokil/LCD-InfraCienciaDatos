import os

import pandas as pd
from sqlalchemy import create_engine, text


DB_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:{os.getenv('SOURCE_DB_PASS', 'admin')}"
    f"@{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432"
    f"/{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
)


def get_engine():
    return create_engine(DB_URI)


def run_query(sql: str) -> pd.DataFrame:
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        return pd.DataFrame(result.fetchall(), columns=list(result.keys()))
