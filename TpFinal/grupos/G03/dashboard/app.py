import streamlit as st

from db import run_query


st.set_page_config(
    page_title="CityBikes G03",
    page_icon="\U0001F6B2",
    layout="wide",
)

st.title("CityBikes · Ecobici Buenos Aires")

st.markdown(
    """
    Dashboard del **Grupo 03** para el TP Final de
    Infraestructura para Ciencia de Datos.

    El pipeline procesa snapshots de estaciones de Ecobici:

    **CityBikes API ? Bronze ? Silver ? Gold ? Dashboard**
    """
)

try:
    kpis = run_query(
        """
        SELECT
            (SELECT COUNT(*)
             FROM gold.dim_estacion) AS estaciones,

            (SELECT COUNT(*)
             FROM gold.dim_zona) AS zonas,

            (SELECT COUNT(*)
             FROM gold.fact_ocupacion_por_hora) AS hechos,

            (SELECT MAX(last_snapshot_at_utc)
             FROM gold.fact_ocupacion_por_hora) AS ultima_actualizacion;
        """
    )

    if not kpis.empty:

        row = kpis.iloc[0]

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Estaciones",
            int(row["estaciones"]),
        )

        c2.metric(
            "Zonas",
            int(row["zonas"]),
        )

        c3.metric(
            "Registros hora",
            int(row["hechos"]),
        )

        st.caption(
            f"Último snapshot procesado: "
            f"{row['ultima_actualizacion']}"
        )

except Exception as exc:

    st.warning(
        "Gold todavía no está disponible. "
        "Ejecutá el pipeline Bronze ? Silver ? Gold."
    )

    st.caption(str(exc))


st.info(
    """
    Abrí la página **Gold · Ocupación** desde el menú lateral
    para consultar saturación, patrones horarios y disponibilidad.
    """
)
