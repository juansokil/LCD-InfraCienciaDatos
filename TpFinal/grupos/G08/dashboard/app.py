import streamlit as st


st.set_page_config(
    page_title="TP Final G08 - Open-Meteo",
    layout="wide",
)

st.title("TP Final G08 - Open-Meteo")
st.caption("Infraestructura base del proyecto")

st.info(
    "Dashboard placeholder. Las visualizaciones reales sobre tablas Gold "
    "se agregaran en una proxima etapa."
)

st.markdown(
    """
    Stack base disponible:

    - Airflow para orquestar DAGs.
    - PostgreSQL con schemas Bronze, Silver y Gold.
    - Streamlit para el dashboard final.
    """
)
