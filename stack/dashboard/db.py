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


# =============================================================================
# FRESCURA — una sola definicion para todo el dashboard
# =============================================================================
# Un numero sin frescura no es informacion: es un numero. La clase06 lo dice
# explicito ("si solo tenes el dashboard, ves numeros pero no sabes si estan
# actualizados"), asi que el tablero tiene que responderlo, no ilustrarlo.
#
# Antes este calculo estaba COPIADO en las paginas de Bronze y de Mercado, con
# los mismos umbrales pero etiquetas distintas ("INGESTA AL DIA" vs "AL DIA"):
# el mismo estado se llamaba de dos formas en el mismo tablero.
UMBRAL_OK, UMBRAL_DEMORA = 30, 90   # minutos


@st.cache_data(ttl=60)
def frescura(schema: str, tabla: str, col: str = "snapshot_ts") -> dict:
    """Cuan viejo es el dato mas reciente de una tabla.

    Devuelve ``{"ts", "minutos", "estado", "etiqueta"}``. ``estado`` es uno de
    ``al_dia`` / ``demorado`` / ``detenido`` / ``sin_datos``, pensado para
    elegir color; ``etiqueta`` ya viene lista para mostrar.

    El pipeline corre cada 15 minutos, asi que 30' de margen es un ciclo
    perdido (tolerable) y 90' son seis (algo se rompio).
    """
    ts = get_last_updated(schema, tabla, col)
    if ts is None:
        return {"ts": None, "minutos": None, "estado": "sin_datos",
                "etiqueta": "sin datos"}
    minutos = (pd.Timestamp.utcnow().tz_localize(None)
               - pd.Timestamp(ts).tz_localize(None)).total_seconds() / 60
    if minutos <= UMBRAL_OK:
        estado = "al_dia"
    elif minutos <= UMBRAL_DEMORA:
        estado = "demorado"
    else:
        estado = "detenido"
    if minutos < 60:
        cuanto = f"hace {minutos:.0f} min"
    elif minutos < 60 * 24:
        cuanto = f"hace {minutos / 60:.1f} h"
    else:
        cuanto = f"hace {minutos / 1440:.1f} dias"
    return {"ts": ts, "minutos": minutos, "estado": estado, "etiqueta": cuanto}


# =============================================================================
# TRANSPARENCIA — de donde sale cada numero
# =============================================================================
@st.cache_data(ttl=300)
def definicion_vista(vista: str) -> str:
    """El SQL REAL de una vista de la capa semantica, traido de Postgres.

    ``pg_get_viewdef`` devuelve la definicion vigente, no una copia pegada en
    la pagina: si la vista cambia, esto cambia solo. Es la diferencia entre
    documentar y mostrar.
    """
    try:
        df = run_query(
            f"SELECT pg_get_viewdef('{vista}'::regclass, true) AS sql"
        )
        return df.iloc[0]["sql"] if not df.empty else ""
    except Exception:
        return ""


# =============================================================================
# ESTADO DEL PIPELINE — la metadata de Airflow
# =============================================================================
# El contenedor del dashboard vive en la misma red que `airflow_db` y ya recibe
# AF_DB_USER/PASS/NAME por su env_file: puede leer la metadata sin tocar el
# compose. Es de SOLO LECTURA -- el dashboard observa, no orquesta.
AIRFLOW_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('AF_DB_USER', 'airflow')}:{os.getenv('AF_DB_PASS', 'airflow')}"
    f"@{os.getenv('AF_DB_HOST', 'airflow_db')}:5432"
    f"/{os.getenv('AF_DB_NAME', 'airflow')}"
)


@st.cache_resource
def get_airflow_engine():
    return create_engine(AIRFLOW_URI)


@st.cache_data(ttl=60)
def estado_pipeline(dags=("crypto_bronze", "crypto_silver",
                          "crypto_gold", "crypto_ml")) -> pd.DataFrame:
    """Ultima corrida de cada DAG de la cadena, leida de Airflow.

    Columnas: ``dag_id, estado, ultima, corridas, fallidas, pausado``.
    DataFrame vacio si Airflow no esta accesible -- el dashboard tiene que
    seguir mostrando datos aunque el orquestador este caido (son dos
    preguntas distintas, y esa distincion es justo la leccion).
    """
    sql = """
        SELECT d.dag_id,
               d.is_paused                                        AS pausado,
               count(r.run_id)                                    AS corridas,
               count(*) FILTER (WHERE r.state = 'failed')          AS fallidas,
               max(r.start_date)                                  AS ultima,
               (array_agg(r.state ORDER BY r.start_date DESC NULLS LAST))[1]
                                                                  AS estado
        FROM dag d
        LEFT JOIN dag_run r ON r.dag_id = d.dag_id
        WHERE d.dag_id = ANY(:dags)
        GROUP BY d.dag_id, d.is_paused
    """
    try:
        engine = get_airflow_engine()
        with engine.connect() as conn:
            res = conn.execute(text(sql), {"dags": list(dags)})
            df = pd.DataFrame(res.fetchall(), columns=list(res.keys()))
        orden = {d: i for i, d in enumerate(dags)}
        return df.sort_values("dag_id", key=lambda s: s.map(orden))
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def eventos_asset(horas: int = 24) -> int:
    """Cuantos assets se publicaron en las ultimas N horas.

    Es la evidencia de que el encadenado data-aware esta VIVO: si bronze corre
    pero no emite, silver nunca arranca y nada falla en rojo.
    """
    try:
        engine = get_airflow_engine()
        with engine.connect() as conn:
            return conn.execute(text(
                "SELECT count(*) FROM asset_event "
                "WHERE timestamp > now() - make_interval(hours => :h)"
            ), {"h": horas}).scalar() or 0
    except Exception:
        return 0
