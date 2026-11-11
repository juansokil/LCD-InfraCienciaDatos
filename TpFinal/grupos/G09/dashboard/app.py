import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

st.set_page_config(page_title="G09 - Clima PBA", layout="wide")

URL = (
    f"postgresql+psycopg2://{os.environ['SOURCE_DB_USER']}:{os.environ['SOURCE_DB_PASS']}"
    f"@{os.environ.get('SOURCE_DB_HOST', 'data_warehouse')}:{os.environ.get('SOURCE_DB_PORT', '5432')}"
    f"/{os.environ['SOURCE_DB_NAME']}"
)
engine = create_engine(URL)

st.title("G09 - Clima en la provincia de Buenos Aires")
st.caption("Dashboard en construcción: los gráficos van a leer las tablas de la capa Gold.")


@st.cache_data(ttl=60)
def tablas_por_capa():
    consulta = text("""
        SELECT table_schema AS capa, table_name AS tabla
        FROM information_schema.tables
        WHERE table_schema IN ('bronze', 'silver', 'gold')
        ORDER BY 1, 2
    """)
    with engine.connect() as conn:
        return pd.read_sql(consulta, conn)


try:
    tablas = tablas_por_capa()
except Exception as error:
    st.error(f"No se pudo conectar al data warehouse: {error}")
    st.stop()

if tablas[tablas["capa"] == "gold"].empty:
    st.info("Esperando datos: el pipeline todavía no generó tablas en la capa Gold.")

st.subheader("Estado del pipeline: tablas por capa")
st.dataframe(tablas)