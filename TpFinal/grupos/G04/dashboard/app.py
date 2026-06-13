"""
Dashboard CityBikes — TP Final G04
Pagina de entrada. Las vistas de negocio estan en pages/1_Gold.py.
Consume EXCLUSIVAMENTE el schema gold.
"""
import streamlit as st

from db import run_query

st.set_page_config(
    page_title="CityBikes — G04",
    page_icon="🚲",
    layout="wide",
)

st.title("🚲 CityBikes — Disponibilidad de bicicletas públicas")
st.caption("TP Final · Grupo 04 · Pipeline Bronze → Silver → Gold (Airflow + Postgres + Streamlit)")

st.markdown(
    """
Este dashboard responde: **¿qué estaciones se saturan o se quedan sin bicis, y a qué horas?**

- Los datos vienen de la **API pública de CityBikes** (`api.citybik.es/v2`), refrescada cada pocos minutos por Airflow.
- Se procesan en capas **Bronze → Silver → Gold**.
- Esta vista consume **solo las tablas Gold** (el modelo final de negocio).

👉 Abrí la página **Gold** en el menú lateral para ver KPIs, mapa y patrones por hora.
"""
)

# Pequeno chequeo de salud: cuantas filas hay en cada capa Gold
try:
    df = run_query(
        """
        SELECT
            (SELECT count(*) FROM gold.station_current)      AS estaciones,
            (SELECT count(*) FROM gold.fact_station_hourly)  AS filas_hora,
            (SELECT count(*) FROM gold.dim_network)          AS redes
        """
    )
    if not df.empty and int(df.loc[0, "estaciones"]) > 0:
        c1, c2, c3 = st.columns(3)
        c1.metric("Estaciones", int(df.loc[0, "estaciones"]))
        c2.metric("Redes", int(df.loc[0, "redes"]))
        c3.metric("Filas estación·hora", int(df.loc[0, "filas_hora"]))
    else:
        st.info(
            "Todavía no hay datos en Gold. El pipeline tarda unos minutos en poblar las tablas "
            "(Bronze cada 5 min → Silver cada 10 min → Gold cada 15 min). Esperá un rato y refrescá."
        )
except Exception as exc:  # noqa: BLE001
    st.warning(f"No se pudo conectar al warehouse todavía: {exc}")
