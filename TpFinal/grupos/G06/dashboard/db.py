"""Conexion del dashboard al warehouse. Reusable desde todas las paginas."""
import os

import pandas as pd
import sqlalchemy
import streamlit as st


@st.cache_resource
def get_engine():
    user = os.getenv("SOURCE_DB_USER", "admin")
    pwd = os.getenv("SOURCE_DB_PASS", "admin")
    host = os.getenv("SOURCE_DB_HOST", "warehouse")
    port = os.getenv("SOURCE_DB_PORT", "5432")
    name = os.getenv("SOURCE_DB_NAME", "openmeteo")
    return sqlalchemy.create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{name}")


def leer(sql, params=None):
    """Corre una query y devuelve un DataFrame. Si la tabla todavia no existe
    (el pipeline no llego hasta ahi), devuelve None en vez de romper la pagina."""
    try:
        return pd.read_sql(sqlalchemy.text(sql), get_engine(), params=params)
    except Exception:
        return None
