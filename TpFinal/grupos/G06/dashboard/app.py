"""Dashboard G06 — portada y estado del pipeline (ESQUELETO).

Las vistas de negocio (semaforo, confianza del pronostico) van en pages/ y
leen SOLO de Gold.
"""
import streamlit as st

from db import leer

st.set_page_config(page_title="G06 - Clima para viajar", page_icon="🌦️", layout="wide")
st.title("🌦️ ¿Conviene viajar esta semana?")
st.caption("TP Final G06 · Infraestructura para Ciencia de Datos · datos de Open-Meteo")

st.markdown("""
<style>
    .stApp {
        background-color: #EAE5D9;
        color: #343C32;
    }

    h1, h2, h3 {
        color: #35513D !important;
    }

    p, label, [data-testid="stCaptionContainer"] {
        color: #454B42 !important;
    }

    [data-testid="stMetric"] {
        background-color: #F2EFE7;
        border: 1px solid #D2CCBD;
        padding: 18px;
        border-radius: 12px;
    }

    [data-testid="stMetricLabel"],
    [data-testid="stMetricValue"],
    [data-testid="stMetricDelta"] {
        color: #35513D !important;
    }

    [data-testid="stAlert"] {
        background-color: #F2EFE7;
        color: #343C32;
        border-radius: 10px;
    }

    hr {
        border-color: #D2CCBD;
    }
</style>
""", unsafe_allow_html=True)



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
