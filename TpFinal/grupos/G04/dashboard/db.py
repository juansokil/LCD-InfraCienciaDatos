"""Conexion al warehouse, reutilizable desde todas las paginas del dashboard."""
import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text


@st.cache_resource
def get_engine():
    user = os.environ.get("WAREHOUSE_USER", "cb_user")
    pwd = os.environ.get("WAREHOUSE_PASSWORD", "changeme")
    host = os.environ.get("WAREHOUSE_HOST", "warehouse")
    port = os.environ.get("WAREHOUSE_PORT", "5432")
    db = os.environ.get("WAREHOUSE_DB", "citybikes")
    url = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"
    return create_engine(url, pool_pre_ping=True)


@st.cache_data(ttl=60)
def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Ejecuta una query y devuelve un DataFrame. Cachea 60s."""
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})
