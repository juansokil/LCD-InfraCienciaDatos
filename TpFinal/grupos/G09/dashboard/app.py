import streamlit as st

st.set_page_config(page_title="G09 - USGS Earthquakes", layout="wide")
st.title("G09 - USGS Earthquakes")
st.markdown(
    "Dashboard sobre la capa **Gold** del catalogo de sismos de USGS. "
    "Elegi una vista en el menu lateral o desde los accesos de abajo."
)

st.page_link("pages/1_Concentracion.py", label="1. Concentracion de actividad sismica", icon=":material/public:")
st.page_link("pages/2_Relacion.py", label="2. Magnitud, profundidad e intensidad", icon=":material/scatter_plot:")
st.page_link("pages/3_Tablas.py", label="3. Tablas operativas", icon=":material/table:")
