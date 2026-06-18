import streamlit as st


st.set_page_config(
    page_title="TP Final G08 - Open-Meteo",
    layout="wide",
)

st.title("TP Final G08 - Open-Meteo")
st.caption("Dashboard sobre la capa Gold")

st.markdown("Pipeline de datos meteorologicos con arquitectura medallion.")

st.markdown(
    """
    Este dashboard consume exclusivamente tablas del schema `gold`.

    Tabla principal:

    - `gold.weather_daily_summary`

    La pagina **Gold Clima** muestra KPIs, evolucion diaria y comparaciones
    por ciudad a partir de datos agregados por dia.
    """
)

st.info("Abrir la pagina Gold Clima desde el menu lateral.")
