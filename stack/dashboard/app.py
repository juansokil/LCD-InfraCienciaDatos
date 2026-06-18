"""
Dashboard BI - Stack Data Engineering UN-SAM
Pagina principal (placeholder, sin contenido aun).
"""

import streamlit as st

st.set_page_config(
    page_title="Dashboard - Stack DE UN-SAM",
    page_icon="📊",
    layout="wide",
)

st.title("Dashboard del Stack de Data Engineering")
st.caption("Stack Data Engineering - UN-SAM")

st.markdown(
    """
    Este es el espacio del **dashboard BI** que se va a construir a lo largo del curso.

    Por ahora está vacío — el contenido real se va armando clase a clase
    siguiendo la **Arquitectura Medallion**:

    - 🥉 **Bronze** — visualización de datos crudos (clase 03)
    - 🥈 **Silver** — métricas de calidad y pipeline health (clase 04)
    - 🥇 **Gold** — KPIs, ranking, volatilidad, dominancia (clase 05)

    A medida que avances, vas a ir agregando páginas en `stack/dashboard/pages/`
    y van a aparecer automáticamente en el menú lateral de Streamlit.
    """
)

st.divider()
st.caption("Stack Data Engineering UN-SAM | Arquitectura Medallion")
