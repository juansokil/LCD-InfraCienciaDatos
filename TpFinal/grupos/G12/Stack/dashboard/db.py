# Conexion a la base y funciones para leer las tablas de gold
import os
from decimal import Decimal

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

USER = os.getenv("SOURCE_DB_USER", "admin")
PASS = os.getenv("SOURCE_DB_PASS", "admin")
HOST = os.getenv("SOURCE_DB_HOST", "localhost")
DB = os.getenv("SOURCE_DB_NAME", "InfraCienciaDatos")

# colores que usamos en todos los graficos
NARANJA = "#ff6b35"
CELESTE = "#4ea8de"
COLORES_ALERTA = {
    "green": "#2ecc71",
    "yellow": "#f1c40f",
    "orange": "#e67e22",
    "red": "#e74c3c",
    "unknown": "#7f8c8d",
}


@st.cache_resource
def conectar():
    return create_engine(f"postgresql+psycopg2://{USER}:{PASS}@{HOST}:5432/{DB}")


@st.cache_data(ttl=60)
def consulta(sql):
    # pd.read_sql no anda con SQLAlchemy 1.4, asi que armamos el DataFrame a mano
    with conectar().connect() as conn:
        res = conn.execute(text(sql))
        df = pd.DataFrame(res.fetchall(), columns=list(res.keys()))
    # postgres devuelve los numeric como Decimal, los pasamos a float para graficar
    for col in df.columns:
        if df[col].map(lambda x: isinstance(x, Decimal)).any():
            df[col] = pd.to_numeric(df[col])
    return df


def hay_datos():
    try:
        n = consulta("SELECT COUNT(*) AS n FROM gold.fact_terremoto")["n"][0]
        return n > 0
    except Exception:
        return False


def chequear_datos():
    # si gold todavia esta vacio mostramos un aviso en vez de que explote la pagina
    if not hay_datos():
        st.info(
            "Todavía no hay datos en Gold. El DAG corre cada 15 minutos: "
            "esperá a la primera corrida o disparalo a mano desde Airflow (localhost:8080)."
        )
        st.stop()


def boton_actualizar():
    if st.sidebar.button("Actualizar datos"):
        st.cache_data.clear()
        st.rerun()