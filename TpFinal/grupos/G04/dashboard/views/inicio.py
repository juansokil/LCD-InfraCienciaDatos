"""Vista de Inicio del dashboard CityBikes — G04 (contenido; el router/estilos están en app.py)."""
import streamlit as st

from db import run_query
from ui import header, panel

header("TP Final · Grupo 04", "CityBikes — Disponibilidad de bicis públicas",
       "Pipeline de datos end-to-end · Bronze → Silver → Gold · Airflow + PostgreSQL + Streamlit")

# ---------- Pregunta de negocio ----------
st.markdown(
    "<div class='insight'>Este dashboard responde: <b>¿qué estaciones se saturan o se quedan "
    "sin bicis, y a qué horas del día?</b></div>",
    unsafe_allow_html=True,
)

# ---------- Cómo funciona: arquitectura Medallion (tarjetas custom) ----------
st.write("")
panel("Cómo funciona", "De la API pública al dashboard, en una arquitectura Medallion de 3 capas")


def _capa(color, num, nombre, desc):
    return (
        f"<div style='background:#FFFFFF;border:1px solid #ECE3DF;border-top:4px solid {color};"
        f"border-radius:14px;padding:16px 20px;box-shadow:0 8px 22px rgba(43,27,27,.06);"
        f"min-height:128px;display:flex;flex-direction:column;justify-content:center'>"
        f"<div style='display:flex;align-items:center;gap:12px;margin-bottom:.7rem'>"
        f"<div style='background:{color};color:#FFFFFF;border-radius:11px;min-width:40px;height:40px;"
        f"display:flex;align-items:center;justify-content:center;font-weight:800;font-size:1.15rem'>{num}</div>"
        f"<div style='color:{color};font-weight:700;font-size:1.3rem'>{nombre}</div></div>"
        f"<div style='color:#5C5C5C;font-size:.93rem;line-height:1.55'>{desc}</div></div>"
    )


b, s, g = st.columns(3, gap="medium")
b.markdown(_capa("#B87333", "1", "Bronze",
                 "Ingesta <b>cruda</b> de la API tal cual llega — el JSON de cada estación + auditoría "
                 "(timestamp, fuente). No se toca nada."), unsafe_allow_html=True)
s.markdown(_capa("#8C9196", "2", "Silver",
                 "Datos <b>limpios, tipados y validados</b>. Calcula ocupación y flags, y descarta las "
                 "estaciones inactivas."), unsafe_allow_html=True)
g.markdown(_capa("#C9A227", "3", "Gold",
                 "Modelo de <b>negocio</b>: dimensiones + agregados por estación y hora. Es lo único que "
                 "consume el dashboard."), unsafe_allow_html=True)

# ---------- Estado del sistema EN VIVO (mismos KPIs que la presentación) ----------
st.write("")
panel("El estado del sistema, en vivo", "Totales de todas las ciudades trackeadas · se actualizan con el pipeline (cada pocos minutos)")
try:
    df = run_query("""
        SELECT count(*)                                   AS estaciones,
               COALESCE(sum(free_bikes), 0)               AS bicis,
               ROUND(100.0*AVG((free_bikes = 0)::int), 1)  AS pct_vacias,
               ROUND(100.0*AVG((empty_slots = 0)::int), 1) AS pct_llenas,
               (SELECT count(*) FROM gold.dim_network)         AS redes,
               (SELECT count(*) FROM gold.fact_station_hourly) AS filas
        FROM gold.station_current
    """)
    if not df.empty and int(df.loc[0, "estaciones"]) > 0:
        r = df.loc[0]
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Estaciones", f"{int(r['estaciones']):,}".replace(",", "."))
        k2.metric("Bicis disponibles", f"{int(r['bicis']):,}".replace(",", "."))
        k3.metric("% sin bicis", f"{float(r['pct_vacias']):.0f}%", help="Estaciones con 0 bicis (las 3 ciudades)")
        k4.metric("% saturadas", f"{float(r['pct_llenas']):.0f}%", help="Estaciones sin ningún lugar libre")
        st.caption(f"Sobre {int(r['redes'])} redes (ciudades) · "
                   f"{int(r['filas']):,} filas estación·hora acumuladas".replace(",", "."))
    else:
        st.info("Todavía no hay datos en Gold. El pipeline tarda unos minutos en poblar las tablas. Esperá y refrescá.")
except Exception as exc:  # noqa: BLE001
    st.warning(f"No se pudo conectar al warehouse todavía: {exc}")

st.write("")
st.caption("→ Abrí la página **Gold** en el menú de la izquierda para el análisis completo: "
           "KPIs en vivo, mapa de disponibilidad, patrón por hora y estaciones críticas.")
