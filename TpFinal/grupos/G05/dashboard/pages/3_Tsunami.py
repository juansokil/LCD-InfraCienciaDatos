import streamlit as st

from db import run_query

st.title("🌊 Eventos sísmicos con indicador de tsunami")
st.markdown(
    """
    **¿Qué representa el indicador de tsunami?**

    Indica si un evento sísmico tiene asociado el indicador de tsunami
    en los registros de USGS.

    - **1:** Indicador activado.
    - **0:** Indicador no activado.
    - **Sin datos:** No hay información disponible.

    Un indicador activado no significa necesariamente que haya ocurrido
    un tsunami ni que exista una alerta vigente.
    """
)

try:
    resumen = run_query("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE tsunami = 1) AS marcados,
            COUNT(*) FILTER (WHERE tsunami = 0) AS no_marcados,
            COUNT(*) FILTER (WHERE tsunami IS NULL) AS sin_dato
        FROM gold.fact_sismo
    """)
    eventos = run_query("""
        SELECT fecha_evento, magnitud, profundidad_km, zona_reportada,
               latitud, longitud
        FROM gold.v_sismos_tsunami
        ORDER BY fecha_evento DESC
    """)
except Exception as exc:
    st.error(f"No se pudo consultar la información Gold de tsunami: {exc}")
    st.stop()

r = resumen.iloc[0]
total = int(r["total"])
marcados = int(r["marcados"])

porcentaje = (marcados / total * 100) if total > 0 else 0

magnitud_maxima = (
    eventos["magnitud"].max()
    if not eventos.empty and eventos["magnitud"].notna().any()
    else None
)
a, b, c = st.columns(3)
a.metric("Marcados por USGS (1)", int(r["marcados"]))
b.metric("No marcados (0)", int(r["no_marcados"]))
c.metric("Sin dato (NULL)", int(r["sin_dato"]))

if eventos.empty:
    st.info("En el período consultado no hay eventos marcados por USGS con tsunami.")
else:
    st.dataframe(eventos, use_container_width=True, hide_index=True)

st.subheader("Conclusión ")

if total > 0:
    st.markdown(
        f"""
        De un total de **{total:,} eventos sísmicos**, 
        **{marcados:,} ({porcentaje:.2f}%)** tienen el indicador de tsunami activado.

        """
    )

    if magnitud_maxima is not None:
        st.markdown(
            f"La magnitud máxima entre los eventos marcados fue de "
            f"**{magnitud_maxima:.1f}**."
        )
    else:
        st.markdown("No hay magnitudes disponibles para los eventos marcados.")

    st.caption(
        "Estos valores describen los registros de USGS. "
        "No representan alertas vigentes ni confirman tsunamis ocurridos."
    )
else:
    st.info("No hay eventos disponibles para realizar el análisis.")
