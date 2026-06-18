import streamlit as st

st.set_page_config(
    page_title="Weather Data Dashboard",
    page_icon="🌦️",
    layout="wide"
)

st.title("🌦️ Weather Data Pipeline Dashboard")

st.markdown("""
Bienvenido al dashboard del proyecto de Data Engineering.

Este sistema muestra datos procesados en arquitectura **Bronze → Silver → Gold**.
""")

st.sidebar.success("Seleccioná una sección arriba 👆")