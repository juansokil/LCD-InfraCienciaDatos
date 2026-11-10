import streamlit as st

from db import run_query

st.title("🌊 Sismos marcados con tsunami")
st.markdown(
    "Esta página muestra eventos cuyo campo `tsunami` vale 1 en los datos "
    "de USGS. El valor **no significa que exista una alerta vigente**."
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
a, b, c = st.columns(3)
a.metric("Marcados por USGS (1)", int(r["marcados"]))
b.metric("No marcados (0)", int(r["no_marcados"]))
c.metric("Sin dato (NULL)", int(r["sin_dato"]))

if eventos.empty:
    st.info("En el período consultado no hay eventos marcados por USGS con tsunami.")
else:
    st.dataframe(eventos, use_container_width=True, hide_index=True)

st.caption(
    "Conclusión: el indicador resume el campo informativo publicado por USGS; "
    "no sustituye avisos oficiales ni evaluación de peligro costero."
)
