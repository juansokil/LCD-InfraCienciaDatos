"""
Entrypoint del dashboard (Streamlit).

Define la configuracion de la pagina y el menu. Cada pagina vive en su archivo
y lee SOLO las vistas gold.v_* (capa semantica de Gold).
"""

import streamlit as st

st.set_page_config(page_title="Sismos · G11", page_icon="🌎", layout="wide")

menu = st.navigation([
    st.Page("inicio.py", title="Inicio", icon="🌎", default=True),
    st.Page("vistas/1_Mapa.py", title="Mapa", icon="🗺️"),
    st.Page("vistas/2_Regiones_y_magnitudes.py", title="Regiones y magnitudes", icon="📊"),
    st.Page("vistas/3_Sudamerica.py", title="Sudamérica", icon="🧭"),
])
menu.run()
