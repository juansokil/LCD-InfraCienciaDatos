import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

DB_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:{os.getenv('SOURCE_DB_PASS', 'admin')}"
    f"@{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432"
    f"/{os.getenv('SOURCE_DB_NAME', 'CityBikes')}"
)

# Tablas del modelo gold (las arma el DAG citybikes_gold).
TABLAS_GOLD = (
    "dim_estacion",
    "dim_fecha",
    "fact_estacion_hora",
    "fact_episodio_sin_bicis",
    "fact_capacidad_actual",
)


@st.cache_resource
def get_engine():
    return create_engine(DB_URI)


@st.cache_data(ttl=60)
def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Ejecutar SQL (con parametros opcionales) y devolver un DataFrame.

    Con pandas 2.x + SQLAlchemy 1.4, ``pd.read_sql`` no reconoce el Engine
    y cae al path DBAPI legacy, asi que el DataFrame se arma a mano.

    CACHE ttl=60: el pipeline escribe cada 5 minutos; no tiene sentido pedirle
    lo mismo a Postgres en cada click de un selectbox.
    """
    with get_engine().connect() as conn:
        res = conn.execute(text(sql), params or {})
        return pd.DataFrame(res.fetchall(), columns=list(res.keys()))


@st.cache_data(ttl=30)
def gold_listo() -> bool:
    """True si las tablas gold existen y ya tienen estaciones cargadas."""
    faltantes = run_query(
        "SELECT t FROM unnest(CAST(:tablas AS text[])) AS t "
        "WHERE to_regclass('gold.' || t) IS NULL",
        {"tablas": list(TABLAS_GOLD)},
    )
    if not faltantes.empty:
        return False
    return bool(run_query("SELECT EXISTS (SELECT 1 FROM gold.dim_estacion) AS hay")["hay"].iloc[0])


def requiere_gold():
    """Corta la pagina con un aviso mientras el primer ciclo del pipeline no termino.

    Al hacer ``docker compose up`` el dashboard arranca antes que gold: sin este
    chequeo las paginas mostrarian un traceback en vez de un mensaje.
    """
    try:
        listo = gold_listo()
    except Exception as exc:  # base todavia arrancando
        st.info(f"No se pudo consultar la base todavía ({type(exc).__name__}). Reintentá en unos segundos.")
        st.stop()
    if not listo:
        st.info(
            "Gold todavía no tiene datos: el pipeline bronze → silver → gold tarda "
            "unos minutos en completar el primer ciclo después de levantar el stack."
        )
        st.stop()
