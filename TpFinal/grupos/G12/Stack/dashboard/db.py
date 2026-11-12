"""
Conexion a PostgreSQL compartida por todas las paginas del dashboard.

Las credenciales salen del .env del stack (docker compose las inyecta con
env_file). SOURCE_DB_HOST vale `data_warehouse` adentro de Docker; afuera,
para correrlo a mano, cae a localhost.
"""

import os
from decimal import Decimal

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

DB_URI = (
    "postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:{os.getenv('SOURCE_DB_PASS', 'admin')}"
    f"@{os.getenv('SOURCE_DB_HOST', 'localhost')}:{os.getenv('SOURCE_DB_PORT', '5432')}"
    f"/{os.getenv('SOURCE_DB_NAME', 'InfraCienciaDatos')}"
)

# Las tablas que arma transform_gold.py. El dashboard solo lee estas.
TABLAS_GOLD = ["dim_region", "fact_sismos_diarios", "agg_ranking_zonas"]

# 1 tonelada de TNT = 4.184e9 joules. Sirve para que la energia se entienda.
JOULES_POR_TON_TNT = 4.184e9


@st.cache_resource
def get_engine():
    return create_engine(DB_URI, pool_pre_ping=True)


def _a_float(df: pd.DataFrame) -> pd.DataFrame:
    """Postgres devuelve NUMERIC como Decimal; plotly y pandas quieren float."""
    for col in df.columns:
        no_nulos = df[col].dropna()
        if not no_nulos.empty and isinstance(no_nulos.iloc[0], Decimal):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=60)
def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Ejecuta SQL y devuelve un DataFrame.

    Se arma el DataFrame a mano porque pd.read_sql con pandas 2.x y
    SQLAlchemy 1.4 no reconoce el engine (el mismo problema que el
    dashboard del curso). Cache de 60 s: el pipeline corre cada hora.
    """
    with get_engine().connect() as conn:
        res = conn.execute(text(sql), params or {})
        df = pd.DataFrame(res.fetchall(), columns=list(res.keys()))
    return _a_float(df)


def estado_gold() -> tuple[bool, str]:
    """Devuelve (listo, mensaje): si Gold ya tiene las tres tablas con datos."""
    try:
        existentes = run_query(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'gold' AND table_name = ANY(:tablas)",
            {"tablas": TABLAS_GOLD},
        )["table_name"].tolist()
    except Exception as exc:  # la base todavia no levanto, credenciales, etc.
        return False, f"No me pude conectar al warehouse: `{type(exc).__name__}`."

    faltan = [t for t in TABLAS_GOLD if t not in existentes]
    if faltan:
        return False, "Todavía no existen en `gold`: " + ", ".join(f"`{t}`" for t in faltan) + "."

    filas = run_query("SELECT COUNT(*) AS n FROM gold.fact_sismos_diarios")["n"].iloc[0]
    if int(filas) == 0:
        return False, "`gold.fact_sismos_diarios` existe pero está vacía."
    return True, ""


def exigir_gold():
    """Corta la pagina con un aviso amable si Gold no esta listo."""
    listo, mensaje = estado_gold()
    if not listo:
        st.info(
            "🕐 **Gold todavía no tiene datos.** " + mensaje + "\n\n"
            "El DAG `dag_usgs_earthquakes_pipeline` corre Bronze → Silver → Gold "
            "cada hora. Cuando termine la primera corrida, esta página se llena sola "
            "(o tocá **Actualizar datos** en la barra lateral)."
        )
        st.stop()


def boton_actualizar():
    """Boton en la barra lateral que limpia el cache y vuelve a consultar."""
    if st.sidebar.button("🔄 Actualizar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
