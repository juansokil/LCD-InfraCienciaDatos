import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text


def _db_uri():
    return (
        f"postgresql+psycopg2://"
        f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
        f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
        f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:"
        f"{os.getenv('SOURCE_DB_PORT', '5432')}/"
        f"{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
    )


@st.cache_resource
def get_engine():
    return create_engine(_db_uri())


def table_exists(schema: str, table: str) -> bool:
    with get_engine().connect() as conn:
        return bool(conn.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables"
                "  WHERE table_schema = :s AND table_name = :t"
                ")"
            ),
            {"s": schema, "t": table},
        ).scalar())


@st.cache_data(ttl=60)
def run_query(sql: str) -> pd.DataFrame:
    with get_engine().connect() as conn:
        result = conn.execute(text(sql))
        return pd.DataFrame(result.fetchall(), columns=list(result.keys()))


@st.cache_data(ttl=60)
def load_table(schema: str, table: str) -> pd.DataFrame:
    if not table_exists(schema, table):
        return pd.DataFrame()
    return run_query(f"SELECT * FROM {schema}.{table}")
