"""
Dashboard CityBikes — TP Final G04 · Router (st.navigation).
Punto de entrada único: inyecta estilos + barra lateral UNA sola vez y enruta a las
vistas de views/. Cambiar de página es un rerun (sin recargar el navegador) → sin "flash".
Consume EXCLUSIVAMENTE el schema gold.
"""
import streamlit as st

from ui import sidebar, style

st.set_page_config(page_title="CityBikes — G04", page_icon="🚲", layout="wide",
                   initial_sidebar_state="expanded")
style()

inicio = st.Page("views/inicio.py", title="Inicio", icon=":material/home:", default=True)
gold = st.Page("views/gold.py", title="Gold", icon=":material/insights:")

sidebar(inicio, gold)

st.navigation([inicio, gold], position="hidden").run()
