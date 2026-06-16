import os
from decimal import Decimal

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
        rows = result.fetchall()
        cols = list(result.keys())
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows, columns=cols)
    for col in df.columns:
        if df[col].map(lambda v: isinstance(v, Decimal)).any():
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=60)
def load_table(schema: str, table: str) -> pd.DataFrame:
    if not table_exists(schema, table):
        return pd.DataFrame()
    return run_query(f"SELECT * FROM {schema}.{table}")


def coerce_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    for col in cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("float64")
    return out
