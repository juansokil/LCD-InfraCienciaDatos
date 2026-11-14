"""Dashboard G06 — portada y estado del pipeline (ESQUELETO).

Las vistas de negocio (semaforo, confianza del pronostico) van en pages/ y
leen SOLO de Gold.
"""
import streamlit as st

from db import leer

st.set_page_config(page_title="G06 - Clima para viajar", page_icon="🌦️", layout="wide")
st.title("🌦️ ¿Conviene viajar esta semana?")
st.caption("TP Final G06 · Infraestructura para Ciencia de Datos · datos de Open-Meteo")

st.subheader("Estado del pipeline")
cols = st.columns(3)
for col, capa in zip(cols, ["bronze", "silver", "gold"]):
    df = leer(f"SELECT count(*) AS n, max(corrida_ts) AS ultima FROM {capa}.esqueleto_ping")
    if df is None or df["n"].iloc[0] == 0:
        col.metric(capa.capitalize(), "sin datos todavia")
    else:
        col.metric(capa.capitalize(), f"{int(df['n'].iloc[0])} corridas",
                   f"ultima: {df['ultima'].iloc[0]:%d/%m %H:%M}")

st.info("Si Gold muestra corridas, la cadena Bronze → Silver → Gold se disparo sola.")
