import os
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

DB_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:{os.getenv('SOURCE_DB_PASS', 'admin')}"
    f"@{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432"
    f"/{os.getenv('SOURCE_DB_NAME', 'cityBikes')}"
)


@st.cache_resource
def get_engine():
    return create_engine(DB_URI)


def table_exists(engine, schema, table):
    """Verificar si una tabla existe en la base de datos."""
    query = text(
        "SELECT EXISTS ("
        "  SELECT 1 FROM information_schema.tables"
        "  WHERE table_schema = :schema AND table_name = :table"
        ")"
    )
    with engine.connect() as conn:
        return conn.execute(query, {"schema": schema, "table": table}).scalar()


@st.cache_data(ttl=60)
def run_query(sql: str) -> pd.DataFrame:
    """Ejecutar SQL y devolver un DataFrame.

    Con pandas 2.x + SQLAlchemy 1.4, ``pd.read_sql`` no reconoce el Engine
    NI la Connection y cae al path DBAPI legacy -> ``.cursor()`` falla.
    Ejecutamos con ``conn.execute(text(...))`` (mismo patron que el resto
    de este modulo) y armamos el DataFrame a mano.

    CACHE ttl=60: el pipeline escribe cada 15 minutos, asi que pedirle lo
    mismo a Postgres en cada rerun (cada click de un selectbox) es tirar
    trabajo. El boton "Actualizar" del encabezado hace ``cache_data.clear()``.
    El caché vive ACA y no en cada pagina a proposito: antes cada una definia
    su propio wrapper ``q()`` -- seis copias de la misma funcion.
    """
    engine = get_engine()
    with engine.connect() as conn:
        res = conn.execute(text(sql))
        return pd.DataFrame(res.fetchall(), columns=list(res.keys()))


@st.cache_data(ttl=60)
def load_table(schema, table):
    """Cargar una tabla completa desde PostgreSQL."""
    engine = get_engine()
    if not table_exists(engine, schema, table):
        return pd.DataFrame()
    return run_query(f"SELECT * FROM {schema}.{table}")