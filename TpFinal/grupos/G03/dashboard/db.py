import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text


DB_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
    f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
    f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
    f"{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
)


@st.cache_resource
def get_engine():
    return create_engine(DB_URI)


@st.cache_data(ttl=60)
def run_query(sql: str, params=None) -> pd.DataFrame:
    engine = get_engine()

    with engine.connect() as conn:
        result = conn.execute(
            text(sql),
            params or {},
        )

        return pd.DataFrame(
            result.fetchall(),
            columns=result.keys(),
        )
