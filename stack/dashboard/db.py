"""
Conexion compartida a PostgreSQL para todas las paginas del dashboard.
"""

import os
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

DB_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:{os.getenv('SOURCE_DB_PASS', 'admin')}"
    f"@{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432"
    f"/{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
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
def load_table(schema, table):
    """Cargar una tabla completa desde PostgreSQL."""
    engine = get_engine()
    if not table_exists(engine, schema, table):
        return pd.DataFrame()
    return pd.read_sql(f"SELECT * FROM {schema}.{table}", engine)


@st.cache_data(ttl=60)
def get_last_updated(schema, table, col="ingested_at"):
    """Obtener el timestamp mas reciente de una tabla."""
    engine = get_engine()
    if not table_exists(engine, schema, table):
        return None
    query = text(f"SELECT MAX({col}) FROM {schema}.{table}")
    with engine.connect() as conn:
        result = conn.execute(query).scalar()
    return result


@st.cache_data(ttl=60)
def get_row_count(schema, table):
    """Obtener cantidad de filas de una tabla."""
    engine = get_engine()
    if not table_exists(engine, schema, table):
        return 0
    query = text(f"SELECT COUNT(*) FROM {schema}.{table}")
    with engine.connect() as conn:
        return conn.execute(query).scalar()


@st.cache_data(ttl=60)
def get_table_list(schema):
    """Listar tablas de un schema."""
    engine = get_engine()
    query = text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = :schema ORDER BY table_name"
    )
    with engine.connect() as conn:
        rows = conn.execute(query, {"schema": schema}).fetchall()
    return [r[0] for r in rows]


def show_last_updated_badge(schema, table, col="ingested_at"):
    """Mostrar badge con ultima actualizacion."""
    ts = get_last_updated(schema, table, col)
    if ts:
        st.caption(f"Ultima actualizacion: **{ts}**")
    else:
        st.caption("Sin datos aun")
