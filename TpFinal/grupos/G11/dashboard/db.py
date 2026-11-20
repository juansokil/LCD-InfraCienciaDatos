"""
Conexion al warehouse para todas las paginas del dashboard.

El dashboard lee SOLO la capa Gold, y dentro de Gold solo las vistas gold.v_*
(la capa semantica). Si una vista todavia no existe (el pipeline recien
arranca), devolvemos un DataFrame vacio y la pagina muestra un aviso.
"""

import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

DB_URI = (
    "postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:{os.getenv('SOURCE_DB_PASS', 'admin')}"
    f"@{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432"
    f"/{os.getenv('SOURCE_DB_NAME', 'sismos')}"
)


@st.cache_resource
def _engine():
    return create_engine(DB_URI, pool_pre_ping=True)


@st.cache_data(ttl=60)
def consultar(sql: str) -> pd.DataFrame:
    """Corre un SELECT sobre Gold. Cache de 60 s: el pipeline escribe cada 30 min."""
    try:
        with _engine().connect() as conn:
            return pd.read_sql(text(sql), conn)
    except Exception as exc:  # la vista todavia no existe, o la base no responde
        print(f"[dashboard] consulta fallida: {exc}")
        return pd.DataFrame()


def sin_datos_aun() -> None:
    st.info(
        "Todavía no hay datos en Gold. Al levantar el stack, Airflow baja los "
        "sismos del último mes y en un par de minutos se encadenan Bronze -> "
        "Silver -> Gold. Refrescá la página en un ratito.",
        icon="⏳",
    )
