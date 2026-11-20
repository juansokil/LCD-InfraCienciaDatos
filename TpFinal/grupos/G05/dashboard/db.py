import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text


@st.cache_resource
def get_engine():
    user = os.getenv("SOURCE_DB_USER", "admin")
    password = os.getenv("SOURCE_DB_PASS", "admin")
    host = os.getenv("SOURCE_DB_HOST", "data_warehouse")
    database = os.getenv("SOURCE_DB_NAME", "InfraCienciaDatos")
    return create_engine(
        f"postgresql+psycopg2://{user}:{password}@{host}:5432/{database}"
    )


@st.cache_data(ttl=60)
def run_query(sql: str) -> pd.DataFrame:
    with get_engine().connect() as conn:
        result = conn.execute(text(sql))
        return pd.DataFrame(result.fetchall(), columns=list(result.keys()))
