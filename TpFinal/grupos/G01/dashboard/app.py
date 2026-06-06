import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from db import get_engine, test_connection

st.set_page_config(
    page_title="Weather Pipeline — G01",
    page_icon="🌤️",
    layout="wide"
)

st.title("🌤️ Weather Pipeline — G01")
st.caption(
    "Pipeline de datos meteorológicos para Argentina · "
)
st.divider()

ok, error = test_connection()
if not ok:
    st.error(f"❌ Sin conexión al Data Warehouse: {error}")
    st.stop()

@st.cache_data(ttl=1800)
def cargar_estado_pipeline():
    engine = get_engine()
    with engine.connect() as conn:

        def q(sql):
            return conn.execute(__import__("sqlalchemy").text(sql)).fetchone()

        bronze = q("""
            SELECT COUNT(*), MAX(ingested_at),
                   COUNT(DISTINCT DATE(ingested_at))
            FROM bronze.open_meteo_raw
        """)
        silver_actual = q("""
            SELECT COUNT(*), MAX(actualizado_at)
            FROM silver.clima_actual
        """)
        silver_pron = q("""
            SELECT COUNT(*), MAX(calculado_at)
            FROM silver.clima_pronostico
        """)
        gold_diario = q("""
            SELECT COUNT(*), MAX(registro_at),
                   COUNT(DISTINCT fecha)
            FROM gold.fact_clima_diario
        """)
        gold_desv = q("""
            SELECT COUNT(*),
                   ROUND(AVG(error_max_c)::NUMERIC, 2),
                   ROUND(AVG(CASE WHEN acierto_lluvia
                       THEN 1.0 ELSE 0.0 END) * 100, 1)
            FROM gold.fact_desvio_pronostico
        """)

    return {
        "bronze":         bronze,
        "silver_actual":  silver_actual,
        "silver_pron":    silver_pron,
        "gold_diario":    gold_diario,
        "gold_desv":      gold_desv,
    }

data = cargar_estado_pipeline()
now  = datetime.now(timezone.utc).replace(tzinfo=None)

def hrs_desde(ts):
    if ts is None:
        return None
    return (now - ts).total_seconds() / 3600

def estado_capa(ts, umbral_warn=2, umbral_err=4):
    hrs = hrs_desde(ts)
    if hrs is None:     return "⚪ Sin datos"
    if hrs < umbral_warn: return f"🟢 Hace {hrs:.1f}hs"
    if hrs < umbral_err:  return f"🟡 Hace {hrs:.1f}hs"
    return f"🔴 Hace {hrs:.1f}hs"

st.subheader("Estado del pipeline")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("**🥉 Bronze**")
    st.markdown(estado_capa(data["bronze"][1]))
    st.metric("Ingestas totales",  data["bronze"][0])
    st.metric("Días acumulados",   data["bronze"][2])

with col2:
    st.markdown("**🥈 Silver**")
    st.markdown(estado_capa(data["silver_actual"][1]))
    st.metric("Mediciones reales", data["silver_actual"][0])
    st.metric("Pronósticos",       data["silver_pron"][0])

with col3:
    st.markdown("**🥇 Gold**")
    st.markdown(estado_capa(data["gold_diario"][1]))
    st.metric("Hechos diarios",    data["gold_diario"][0])
    st.metric("Evaluaciones",      data["gold_desv"][0])

st.divider()

st.subheader("Métricas del modelo")

error_prom = data["gold_desv"][1]
pct_lluvia = data["gold_desv"][2]
dias_gold  = data["gold_diario"][2]

col4, col5, col6 = st.columns(3)
col4.metric(
    "Días de historial",
    dias_gold,
    help="Días completos procesados en Gold"
)
col5.metric(
    "Error promedio pronóstico",
    f"{error_prom}°C" if error_prom else "—",
    help="Error absoluto medio en temperatura máxima"
)
col6.metric(
    "Precisión predicción lluvia",
    f"{pct_lluvia}%" if pct_lluvia else "—",
    help="% de días donde el pronóstico de lluvia fue correcto"
)

st.divider()

col7, col8 = st.columns([1, 1])

with col7:
    st.subheader("Regiones monitoreadas")
    st.markdown("""
    | Provincia | Coordenadas |
    |---|---|
    | Buenos Aires | -34.60°, -58.38° |
    | Córdoba | -31.41°, -64.18° |
    | Mendoza | -32.89°, -68.85° |
    | Salta | -24.79°, -65.41° |
    | Tierra del Fuego | -54.80°, -68.30° |
    """)

with col8:
    st.subheader("Arquitectura del pipeline")
    st.markdown("""
    | Capa | Tabla | Contenido |
    |---|---|---|
    | 🥉 Bronze | `open_meteo_raw` | JSON crudo de la API |
    | 🥈 Silver | `clima_actual` | Mediciones reales limpias |
    | 🥈 Silver | `clima_pronostico` | Pronósticos desanidados |
    | 🥇 Gold | `fact_clima_diario` | Métricas agregadas por día |
    | 🥇 Gold | `fact_desvio_pronostico` | Precisión del pronóstico |
    """)