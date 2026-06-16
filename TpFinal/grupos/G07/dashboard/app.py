"""
Dashboard principal del TP Final - Infraestructura para Ciencia de Datos (UNSAM)
"""

import streamlit as st

st.set_page_config(
    page_title="EcoBici Analytics",
    page_icon="🚲",
    layout="wide",
)

st.title("🚲 EcoBici Analytics")
st.subheader("Monitoreo operativo del sistema de bicicletas públicas de la Ciudad de Buenos Aires")

st.markdown(
    """
    Este dashboard fue desarrollado como trabajo final de la materia
    **Infraestructura para Ciencia de Datos (UNSAM)**.

    Utilizando una arquitectura **Medallion**, el proyecto transforma datos
    publicados por la API de CityBikes en información útil para apoyar la
    gestión operativa del sistema **EcoBici**.
    """
)

st.divider()

st.header("🎯 Objetivos")

st.markdown(
    """
    El objetivo es brindar herramientas que permitan responder preguntas como:

    - ¿Cómo varía la disponibilidad de bicicletas a lo largo del día?
    - ¿Qué estaciones presentan mayores problemas de saturación o desabastecimiento?
    - ¿Qué zonas requieren mayor atención operativa?
    - ¿Cuál es el estado actual de la red?
    - ¿Qué estaciones son recurrentemente problemáticas?
    """
)

st.divider()

st.header("🏗️ Arquitectura del proyecto")

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("🥉 Bronze")
    st.markdown(
        """
        Datos crudos obtenidos desde la API.

        - Snapshots de disponibilidad.
        - Información de estaciones.
        - Información de redes.
        """
    )

with col2:
    st.subheader("🥈 Silver")
    st.markdown(
        """
        Datos limpios y enriquecidos.

        - Estandarización de esquemas.
        - Cálculo de indicadores derivados.
        - Enriquecimiento geográfico.
        """
    )

with col3:
    st.subheader("🥇 Gold")
    st.markdown(
        """
        Modelo analítico orientado a la toma de decisiones.

        - Disponibilidad agregada por hora.
        - Estado actual de estaciones.
        - Identificación de estaciones críticas.
        - Visualizaciones operativas.
        """
    )

st.divider()

st.header("👥 Equipo")

st.markdown(
    """
    Trabajo realizado por el **Grupo G07**
    - Gonzalo Cárdenas (@Zagon22)
    - Gabriela Gattas (@Gabi6285)
    - Gastón Rossi (@torino05)
    - Morena Stolerman (@Morenastolerman)
    - Camila Vidoni (@camilavidoni7)
    - Alex Flores (@afloreschoquehuanca-byte)
    """
)

st.caption("TP Final · Arquitectura Medallion · CityBikes / EcoBici")
