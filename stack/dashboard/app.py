"""
Dashboard BI - Crypto Markets
Pagina principal con navegacion multipagina.
"""

import streamlit as st

st.set_page_config(
    page_title="Crypto Dashboard - UN-SAM",
    page_icon="📊",
    layout="wide",
)

st.title("Crypto Markets Dashboard")
st.caption("Stack Data Engineering - UN-SAM")

st.markdown(
    """
    ### Paginas disponibles

    Usa el menu lateral para navegar entre las distintas vistas:

    **Data Layers**
    - **Bronze** — Datos crudos, estado de tablas, explorador
    - **Silver** — Data quality, pipeline health, quarantine, columnas derivadas

    **Gold / Analytics**
    - **Resumen Mercado** — KPIs, Top 10, ganadores y perdedores del dia
    - **Ranking Precios** — Tabla interactiva con filtros y comparador de criptos
    - **Volatilidad Riesgo** — Spread, mapa de riesgo, distancia al ATH
    - **Dominancia** — Participacion de mercado, concentracion, price tiers
    """
)

st.divider()
st.caption("Stack Data Engineering UN-SAM | Arquitectura Medallion")
