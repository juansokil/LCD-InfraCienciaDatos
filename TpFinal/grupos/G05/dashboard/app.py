import streamlit as st

# Configuración principal de la aplicación
st.set_page_config(page_title="Dashboard Climático - G05", page_icon="🌤️", layout="wide")

st.title("🌤️ Pipeline Meteorológico - Grupo 05")
st.markdown("""
Bienvenido al dashboard del pipeline de datos climáticos de Argentina.

Este proyecto ingesta datos de la API **Open-Meteo** para 4 ciudades argentinas
y los procesa a través de una arquitectura **Bronze → Silver → Gold**.

### Ciudades monitoreadas
- Jujuy
- Mendoza
- Buenos Aires
- Ushuaia

Navegá a la sección **Gold** en el menú de la izquierda para ver el análisis completo.
""")
