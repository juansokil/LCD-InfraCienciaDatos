import pandas as pd
import streamlit as st

from db import run_query


st.set_page_config(
    page_title="CityBikes G03",
    page_icon="\U0001F6B2",
    layout="wide",
)


# =========================================================
# ENCABEZADO
# =========================================================

st.title(
    "CityBikes · Ecobici Buenos Aires"
)

st.markdown(
    """
    Dashboard del **Grupo 03** para el TP Final de
    **Infraestructura para Ciencia de Datos**.

    El proyecto procesa snapshots de disponibilidad de las
    estaciones de Ecobici mediante una arquitectura Medallion:

    **CityBikes API → Bronze → Silver → Gold → Dashboard**
    """
)

st.info(
    "El análisis se centra en disponibilidad, ocupación, "
    "distribución territorial y evolución temporal de las estaciones. "
    "Los datos representan snapshots y no viajes individuales."
)


# =========================================================
# KPIs GENERALES DEL MODELO GOLD
# =========================================================

try:

    kpis = run_query(
        """
        SELECT
            (
                SELECT COUNT(*)
                FROM gold.dim_estacion
            ) AS estaciones,

            (
                SELECT COUNT(*)
                FROM gold.dim_zona
            ) AS zonas,

            (
                SELECT COUNT(*)
                FROM gold.fact_ocupacion_por_hora
            ) AS hechos,

            (
                SELECT MAX(last_snapshot_at_utc)
                FROM gold.fact_ocupacion_por_hora
            ) AS ultima_actualizacion;
        """
    )


    if not kpis.empty:

        row = kpis.iloc[0]


        c1, c2, c3 = st.columns(
            3
        )


        c1.metric(
            "Estaciones",
            int(
                row["estaciones"]
            ),
        )


        c2.metric(
            "Zonas",
            int(
                row["zonas"]
            ),
        )


        c3.metric(
            "Registros estación × hora",
            int(
                row["hechos"]
            ),
        )


        ultima_actualizacion = pd.to_datetime(
            row["ultima_actualizacion"],
            utc=True,
            errors="coerce",
        )


        if pd.notna(
            ultima_actualizacion
        ):

            ultima_local = (
                ultima_actualizacion
                .tz_convert(
                    "America/Argentina/Buenos_Aires"
                )
            )

            ultima_texto = (
                ultima_local.strftime(
                    "%d/%m/%Y %H:%M"
                )
            )

            st.caption(
                "Último snapshot procesado: "
                f"{ultima_texto} hs"
            )


except Exception as exc:

    st.warning(
        "La capa Gold todavía no está disponible. "
        "El pipeline debe completar "
        "Bronze → Silver → Gold."
    )

    st.caption(
        str(exc)
    )


# =========================================================
# ACCESO AL ANÁLISIS
# =========================================================

st.markdown(
    """
    ### ¿Qué permite analizar el dashboard?

    La página **Gold · Ocupación** permite responder tres preguntas:

    - **¿Dónde hay problemas de disponibilidad?**
    - **¿Cómo se distribuyen territorialmente?**
    - **¿Cómo cambian a lo largo del tiempo?**
    """
)


st.info(
    """
    Abrí **Gold · Ocupación** desde el menú lateral para explorar
    disponibilidad para retiro y devolución, análisis por barrio y comuna,
    mapa de estaciones y evolución horaria.
    """
)