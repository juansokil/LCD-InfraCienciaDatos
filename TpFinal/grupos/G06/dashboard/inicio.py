
"""
Dashboard G06 — Inicio.
Portada principal del Semáforo del Viajero.
"""

import streamlit as st

st.set_page_config(
    page_title="Semáforo del Viajero",
    page_icon="🌿",
    layout="wide"
)

from tema import aplicar_tema


def mostrar_inicio():

    aplicar_tema()

    # Identidad visual
    with st.sidebar:
        st.markdown("# 🌿")
        st.markdown("### SEMÁFORO DEL VIAJERO")
        st.caption("Explorá · Compará · Elegí")

    # Presentación principal
    st.caption("TU PRÓXIMO VIAJE EMPIEZA ACÁ")

    with st.container(border=True):
        st.title("¿Cuándo y dónde conviene viajar?")

        st.write(
            """
            Explorá las condiciones climáticas históricas de distintos
            destinos de Argentina y descubrí cuáles son las mejores
            épocas para planificar tu próximo viaje.
            """
        )

    st.write("")

    # Destinos
    st.subheader("Descubrí nuestros destinos")

    st.write(
        "Explorá tres destinos argentinos ubicados en distintas regiones del país."
    )

    destinos = st.columns(3)

    destinos_info = [
        ("🏜️", "Purmamarca", "Jujuy · Noroeste"),
        ("🏔️", "Bariloche", "Río Negro · Patagonia"),
        ("🌊", "Puerto Iguazú", "Misiones · Noreste")
    ]

    for col, (icono, nombre, region) in zip(destinos, destinos_info):
        with col:
            with st.container(border=True):
                st.markdown(f"## {icono}")
                st.markdown(f"### {nombre}")
                st.caption(region)

    st.write("")

    # Funcionalidades
    st.subheader("¿Qué podés hacer?")

    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown("## 🚦")
            st.markdown("### Semáforo del viajero")
            st.write(
                """
                Consultá un destino y conocé qué tan favorables
                son sus condiciones climáticas para viajar.
                """
            )

    with col2:
        with st.container(border=True):
            st.markdown("## 📊")
            st.markdown("### Análisis histórico")
            st.write(
                """
                Explorá temperaturas, precipitaciones y días
                agradables. Compará destinos, meses y años.
                """
            )

    st.write("")

    # Aclaración metodológica
    st.info(
        "Las recomendaciones se basan en registros climáticos históricos "
        "de cinco años. No representan un pronóstico meteorológico "
        "en tiempo real."
    )

    # Información del proyecto
    st.divider()

    col_izq, col_centro, col_der = st.columns([1, 2, 1])

    with col_centro:
        st.markdown("**SEMÁFORO DEL VIAJERO · PROYECTO G06**")
        st.caption("Infraestructura para Ciencia de Datos")


# Navegación
paginas = [
    st.Page(
        mostrar_inicio,
        title="Inicio",
        icon="🏡",
        default=True
    ),
    st.Page(
        "pages/semaforo.py",
        title="Semáforo del viajero",
        icon="🚦"
    ),
    st.Page(
        "pages/Analisis_historico.py",
        title="Análisis histórico",
        icon="📊"
    )
]

navegacion = st.navigation(paginas)
navegacion.run()
