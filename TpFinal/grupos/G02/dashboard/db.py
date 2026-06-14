import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text


DB_URI = (
    "postgresql+psycopg2://"
    f"{os.getenv('POSTGRES_USER', 'postgres')}:"
    f"{os.getenv('POSTGRES_PASSWORD', '')}"
    f"@{os.getenv('POSTGRES_HOST', 'data_warehouse')}:5432/"
    f"{os.getenv('POSTGRES_DB', 'exchange')}"
)


@st.cache_resource
def get_engine():
    return create_engine(DB_URI)


def table_exists(schema: str, table: str) -> bool:
    query = text(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = :schema
              AND table_name = :table
        )
        """
    )
    with get_engine().connect() as conn:
        return conn.execute(query, {"schema": schema, "table": table}).scalar()


@st.cache_data(ttl=60)
def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    with get_engine().connect() as conn:
        result = conn.execute(text(sql), params or {})
        return pd.DataFrame(result.fetchall(), columns=list(result.keys()))
